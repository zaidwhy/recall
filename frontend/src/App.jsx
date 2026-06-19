import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AudioPlayer, downsampleTo16k, f32ToInt16 } from "./audio.js";

const CAPTURE_INTERVAL_MS = 2000;
const JPEG_QUALITY = 0.6;
const MAX_WIDTH = 640;
const NARRATE_TIMEOUT_MS = 7000;

function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtRelative(ts) {
  const mins = Math.round((Date.now() / 1000 - ts) / 60);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return new Date(ts * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const streamRef = useRef(null);
  const micCtxRef = useRef(null);
  const workletRef = useRef(null);
  const micSourceRef = useRef(null);
  const playerRef = useRef(null);
  const talkingRef = useRef(false);
  const narrateTimerRef = useRef(null);

  const [running, setRunning] = useState(false);
  const [wsState, setWsState] = useState("idle");
  const [framesSent, setFramesSent] = useState(0);
  const [lastAck, setLastAck] = useState(null);
  const [error, setError] = useState("");
  const [observation, setObservation] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [liveState, setLiveState] = useState("idle");
  const [talking, setTalking] = useState(false);
  const [userText, setUserText] = useState("");
  const [assistantText, setAssistantText] = useState("");
  const [recording, setRecording] = useState(false);
  const [timeline, setTimeline] = useState([]);
  const [ingestCount, setIngestCount] = useState(0);
  const [recalled, setRecalled] = useState(null);
  const [lightbox, setLightbox] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [flashCalls, setFlashCalls] = useState(0);
  const [flashBudget, setFlashBudget] = useState(18);
  const [scanning, setScanning] = useState(false);
  const [nextScanAt, setNextScanAt] = useState(0);
  const [countdown, setCountdown] = useState(0);

  // ── Derived state ────────────────────────────────────────────────────────

  const filteredTimeline = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return timeline;
    return timeline.filter(e =>
      e.location_label?.toLowerCase().includes(q) ||
      e.description?.toLowerCase().includes(q) ||
      e.objects?.some(o => o.toLowerCase().includes(q))
    );
  }, [timeline, searchQuery]);

  const groupedTimeline = useMemo(() => {
    if (!filteredTimeline.length) return [];
    const groups = new Map();
    for (const entry of filteredTimeline) {
      const loc = entry.location_label || "Unknown";
      if (!groups.has(loc)) groups.set(loc, []);
      groups.get(loc).push(entry);
    }
    return [...groups.entries()].sort(([, a], [, b]) => b[0].timestamp - a[0].timestamp);
  }, [filteredTimeline]);

  // ── Derived state (stats) ────────────────────────────────────────────────

  const distinctLocations = useMemo(
    () => new Set(timeline.map(e => e.location_label)).size,
    [timeline]
  );

  // ── Side effects ──────────────────────────────────────────────────────────

  useEffect(() => {
    document.title = timeline.length > 0 ? `Recall (${timeline.length})` : "Recall";
  }, [timeline.length]);

  useEffect(() => {
    if (!nextScanAt) return;
    const tick = () => setCountdown(Math.max(0, Math.round((nextScanAt - Date.now()) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [nextScanAt]);

  useEffect(() => {
    if (!error) return;
    const id = setTimeout(() => setError(""), 8000);
    return () => clearTimeout(id);
  }, [error]);

  // ── Voice helpers ─────────────────────────────────────────────────────────

  const teardownVoice = useCallback(() => {
    clearTimeout(narrateTimerRef.current);
    narrateTimerRef.current = null;
    talkingRef.current = false;
    setTalking(false);
    try { workletRef.current?.disconnect(); } catch { /* ignore */ }
    try { micSourceRef.current?.disconnect(); } catch { /* ignore */ }
    try { micCtxRef.current?.close(); } catch { /* ignore */ }
    playerRef.current?.close();
    workletRef.current = micSourceRef.current = micCtxRef.current = playerRef.current = null;
    setLiveState("idle");
  }, []);

  const startTalk = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || talkingRef.current) return;
    setUserText("");
    setAssistantText("");
    setRecalled(null);
    talkingRef.current = true;
    setTalking(true);
    navigator.vibrate?.(20);
    ws.send(JSON.stringify({ type: "talk_start" }));
  }, []);

  const stopTalk = useCallback(() => {
    if (!talkingRef.current) return;
    talkingRef.current = false;
    setTalking(false);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "talk_end" }));
  }, []);

  const narrate = useCallback(() => {
    if (talkingRef.current) {
      clearTimeout(narrateTimerRef.current);
      narrateTimerRef.current = null;
      stopTalk();
    } else {
      startTalk();
      narrateTimerRef.current = setTimeout(() => {
        stopTalk();
        narrateTimerRef.current = null;
      }, NARRATE_TIMEOUT_MS);
    }
  }, [startTalk, stopTalk]);

  // ── WebSocket setup ───────────────────────────────────────────────────────

  const setupWs = useCallback((ws) => {
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;
    setWsState("connecting");

    ws.onopen = () => {
      setWsState("open");
      if (!timerRef.current) {
        timerRef.current = setInterval(() => {
          const w = wsRef.current;
          if (!w || w.readyState !== WebSocket.OPEN) return;
          const canvas = canvasRef.current;
          const video = videoRef.current;
          if (!video || !canvas || !video.videoWidth) return;
          const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
          canvas.width = Math.round(video.videoWidth * scale);
          canvas.height = Math.round(video.videoHeight * scale);
          canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
          w.send(JSON.stringify({ type: "frame", ts: Date.now(), data: dataUrl }));
          setFramesSent(n => n + 1);
        }, CAPTURE_INTERVAL_MS);
      }
      fetch("/memory")
        .then(r => r.json())
        .then(entries => setTimeline(entries.map(e => ({ ...e, thumbnail: `/thumbnails/${e.id}.jpg` }))))
        .catch(() => {});
      // Auto-start recording after camera settles
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "record_start" }));
      }, 2000);
    };

    ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        playerRef.current?.playInt16(ev.data);
        return;
      }
      try {
        const msg = JSON.parse(ev.data);
        switch (msg.type) {
          case "ack":
            setLastAck(msg);
            break;
          case "observation":
            setObservation(msg);
            setAnalyzing(false);
            break;
          case "scanning":
            setScanning(true);
            break;
          case "ingested":
            setScanning(false);
            setTimeline(prev => [{
              id: msg.id, thumbnail: msg.thumbnail,
              location_label: msg.location_label, description: msg.description,
              objects: msg.objects, timestamp: msg.timestamp,
            }, ...prev]);
            setIngestCount(n => n + 1);
            if (msg.flash_calls != null) { setFlashCalls(msg.flash_calls); setFlashBudget(msg.flash_budget); }
            if (msg.next_scan_at) setNextScanAt(msg.next_scan_at * 1000);
            break;
          case "updated":
            setScanning(false);
            setTimeline(prev => prev.map(e => e.id === msg.id
              ? { ...e, description: msg.description, objects: msg.objects, timestamp: msg.timestamp, thumbnail: msg.thumbnail + "?t=" + Date.now() }
              : e
            ));
            if (msg.flash_calls != null) { setFlashCalls(msg.flash_calls); setFlashBudget(msg.flash_budget); }
            if (msg.next_scan_at) setNextScanAt(msg.next_scan_at * 1000);
            break;
          case "record_status":
            setRecording(msg.recording);
            if (!msg.recording) setScanning(false);
            if (msg.flash_calls != null) { setFlashCalls(msg.flash_calls); setFlashBudget(msg.flash_budget); }
            if (msg.next_scan_at) setNextScanAt(msg.next_scan_at * 1000);
            break;
          case "transcript":
            if (msg.role === "user") setUserText(t => t + msg.text);
            else setAssistantText(t => t + msg.text);
            break;
          case "recalled":
            setRecalled(msg.match);
            break;
          case "live_status":
            setLiveState(msg.state === "open" ? "open" : "idle");
            break;
          case "error":
            setError(msg.detail || "server error");
            setAnalyzing(false);
            setScanning(false);
            break;
        }
      } catch { /* ignore */ }
    };

    ws.onclose = () => {
      setWsState("closed");
      setLiveState("idle");
      setRecording(false);
      setScanning(false);
    };

    ws.onerror = () => setError("WebSocket error — is the backend running on this origin?");
  }, []);

  const reconnectWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }
    setError("");
    setupWs(new WebSocket(wsUrl()));
  }, [setupWs]);

  // ── Camera + WS startup ───────────────────────────────────────────────────

  const stop = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    teardownVoice();
    if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); wsRef.current = null; }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    setRunning(false);
    setWsState("closed");
    setRecording(false);
    setScanning(false);
  }, [teardownVoice]);

  const start = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
        audio: true,
      });
      streamRef.current = stream;
      const video = videoRef.current;
      video.srcObject = stream;
      try {
        await video.play();
      } catch (e) {
        if (e.name !== "AbortError") throw e;
      }
      setRunning(true);
      setupWs(new WebSocket(wsUrl()));
    } catch (e) {
      setError(
        e?.name === "NotAllowedError"
          ? "Camera/mic permission denied. Grant access and retry."
          : `Could not start: ${e?.message || e}. (Needs HTTPS — use the tunnel URL.)`
      );
      stop();
    }
  }, [setupWs, stop]);

  // ── Other actions ─────────────────────────────────────────────────────────

  const grabFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) return null;
    const scale = Math.min(1, MAX_WIDTH / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  }, []);

  const analyzeFrame = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const dataUrl = grabFrame();
    if (!dataUrl) return;
    setObservation(null);
    setAnalyzing(true);
    ws.send(JSON.stringify({ type: "analyze", ts: Date.now(), data: dataUrl }));
  }, [grabFrame]);

  const toggleRecord = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: recording ? "record_stop" : "record_start" }));
  }, [recording]);

  const deleteEntry = useCallback(async (id) => {
    try { await fetch(`/memory/${id}`, { method: "DELETE" }); } catch { /* ignore */ }
    setTimeline(prev => prev.filter(e => e.id !== id));
  }, []);

  const clearAll = useCallback(async () => {
    if (!confirm(`Delete all ${timeline.length} ${timeline.length === 1 ? "memory" : "memories"}? This cannot be undone.`)) return;
    try { await fetch("/memory", { method: "DELETE" }); } catch { /* ignore */ }
    setTimeline([]);
    setIngestCount(0);
    setRecalled(null);
  }, [timeline.length]);

  const startVoice = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) { setError("Start the camera first."); return; }
    if (!streamRef.current) { setError("No microphone stream. Restart the camera."); return; }
    try {
      const player = new AudioPlayer(24000);
      await player.resume();
      playerRef.current = player;

      const Ctx = window.AudioContext || window.webkitAudioContext;
      const micCtx = new Ctx({ sampleRate: 16000 });
      await micCtx.resume();
      await micCtx.audioWorklet.addModule("/pcm-worklet.js");
      const source = micCtx.createMediaStreamSource(streamRef.current);
      const node = new AudioWorkletNode(micCtx, "pcm-capture");
      node.port.onmessage = (e) => {
        if (!talkingRef.current) return;
        const w = wsRef.current;
        if (!w || w.readyState !== WebSocket.OPEN) return;
        w.send(f32ToInt16(downsampleTo16k(e.data, micCtx.sampleRate)).buffer);
      };
      source.connect(node);
      const sink = micCtx.createGain();
      sink.gain.value = 0;
      node.connect(sink);
      sink.connect(micCtx.destination);
      micCtxRef.current = micCtx;
      workletRef.current = node;
      micSourceRef.current = source;

      ws.send(JSON.stringify({ type: "live_start" }));
    } catch (e) {
      setError(`Voice start failed: ${e?.message || e}`);
      teardownVoice();
    }
  }, [teardownVoice]);

  const endVoice = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "live_stop" }));
    teardownVoice();
  }, [teardownVoice]);

  useEffect(() => () => stop(), [stop]);

  // ── Render ────────────────────────────────────────────────────────────────

  const secure = window.isSecureContext;
  const budgetExhausted = flashCalls >= flashBudget;

  return (
    <div className="app">
      <header>
        <h1>Recall</h1>
        <p className="tag">
          {recording
            ? scanning ? "scanning…" : countdown > 0 ? `next scan in ${countdown}s` : "see once · remember always"
            : "see once · remember always"}
        </p>
      </header>

      {!secure && (
        <div className="warn">
          Not a secure context — camera will fail. Open the
          <code> https://*.trycloudflare.com </code> tunnel URL instead.
        </div>
      )}

      {/* Onboarding — shown only before camera starts */}
      {!running && (
        <div className="onboarding">
          <div className="ob-step">
            <div className="ob-num">1</div>
            <div className="ob-body">
              <strong>Start camera</strong>
              <span>Point your phone at the room — recording starts automatically</span>
            </div>
          </div>
          <div className="ob-divider" />
          <div className="ob-step">
            <div className="ob-num">2</div>
            <div className="ob-body">
              <strong>Walk around</strong>
              <span>Recall memorizes each new scene it sees</span>
            </div>
          </div>
          <div className="ob-divider" />
          <div className="ob-step">
            <div className="ob-num">3</div>
            <div className="ob-body">
              <strong>Ask anything</strong>
              <span>"Where are my keys?" and get a spoken answer</span>
            </div>
          </div>
        </div>
      )}

      {/* Camera */}
      <div className="stage">
        <video ref={videoRef} playsInline autoPlay muted />
        <canvas ref={canvasRef} hidden />

        {/* Scanning overlay */}
        {running && recording && scanning && <div className="scan-overlay" />}

        {/* Recording pill */}
        {running && recording && (
          <div className={`recording-pill${budgetExhausted ? " budget-warn" : ""}${scanning ? " pill-scanning" : ""}`}>
            <span className="rec-dot" />
            {scanning
              ? "Scanning…"
              : `REC · ${ingestCount} ${ingestCount === 1 ? "scene" : "scenes"}`}
            {!scanning && !budgetExhausted && (
              <span className="flash-budget">
                {countdown > 0 ? ` · ${countdown}s` : ingestCount > 0 ? " · ready" : ""}
              </span>
            )}
            {budgetExhausted && <span className="flash-budget"> · budget full</span>}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="controls">
        {!running ? (
          <button className="primary" onClick={start}>Start camera</button>
        ) : (
          <>
            <button className={recording ? "record recording" : "record"} onClick={toggleRecord}>
              {recording ? "⏹ Stop" : "⏺ Record"}
            </button>
            <button className="ghost small" onClick={analyzeFrame} disabled={analyzing}>
              {analyzing ? "…" : "Analyze"}
            </button>
            <button className="danger small" onClick={stop}>End</button>
          </>
        )}
      </div>

      {/* Reconnect banner */}
      {running && wsState === "closed" && (
        <div className="ws-banner">
          Connection lost —
          <button className="ws-reconnect" onClick={reconnectWs}>Reconnect</button>
        </div>
      )}

      {/* Empty recording state */}
      {running && recording && timeline.length === 0 && !scanning && (
        <div className="empty-recording">
          <div className="er-icon">👁</div>
          <p>Recall is watching. Move to a new spot to trigger the first scan.</p>
          <p className="er-sub">
            {countdown > 0 ? `Next scan available in ${countdown}s` : "Ready — waiting for a scene change"}
          </p>
        </div>
      )}

      {/* Voice */}
      {running && (
        <div className="voice">
          {liveState === "idle" ? (
            <button className="voice-start" onClick={startVoice}>🎙 Enable voice</button>
          ) : (
            <div className="ptt-area">
              <button
                className={`ptt${talking ? " ptt--active" : ""}`}
                onPointerDown={startTalk}
                onPointerUp={stopTalk}
                onPointerLeave={stopTalk}
                onContextMenu={e => e.preventDefault()}
                aria-label={talking ? "Listening — release to send" : "Hold to ask Recall"}
              >
                <span className="ptt-icon">{talking ? "●" : "🎤"}</span>
                <span className="ptt-label">{talking ? "Listening…" : "Hold to ask"}</span>
              </button>
              <div className="ptt-actions">
                <button className="tap-ask" onClick={narrate}>
                  {talking ? "⏹ Done" : "Tap to ask"}
                </button>
                <button className="ghost small" onClick={endVoice}>End voice</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Transcript */}
      {(userText || assistantText) && (
        <div className="transcript">
          {userText && <p className="t-you">"{userText}"</p>}
          {assistantText && <p className="t-recall">{assistantText}</p>}
        </div>
      )}

      {/* Recalled spotlight */}
      {recalled && (
        <div className="recalled">
          <div className="recalled-badge">
            🧠 Remembered
            <button className="recalled-x" onClick={() => setRecalled(null)}>×</button>
          </div>
          <div className="memory-entry recalled-entry">
            <img
              className="memory-thumb"
              src={recalled.thumbnail}
              alt={recalled.location}
              onClick={() => setLightbox(recalled.thumbnail)}
            />
            <div className="memory-meta">
              <div className="memory-loc">📍 {recalled.location}</div>
              <p className="memory-desc">{recalled.scene_description}</p>
              <div className="chips">
                {(recalled.objects_visible ?? []).map((o, i) => <span key={i} className="chip">{o}</span>)}
              </div>
              <div className="memory-time">{recalled.time_ago}</div>
            </div>
          </div>
        </div>
      )}

      {/* On-demand observation */}
      {observation && (
        <div className="observation">
          <div className="loc">📍 {observation.location_label}</div>
          <p className="desc">{observation.description}</p>
          <div className="chips">
            {observation.objects.map((o, i) => <span key={i} className="chip">{o}</span>)}
          </div>
          <div className="latency">Gemini Flash · {observation.latency_ms} ms</div>
        </div>
      )}

      {error && <div className="error">{error}</div>}

      {/* Memory timeline */}
      {timeline.length > 0 && (
        <div className="timeline">
          <div className="timeline-header">
            <h2 className="timeline-heading">Memory · {timeline.length}</h2>
            <input
              className="search-input"
              type="search"
              placeholder="Search…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>

          {filteredTimeline.length === 0 && (
            <p className="search-empty">No memories match "{searchQuery}"</p>
          )}

          {groupedTimeline.map(([loc, entries]) => (
            <div key={loc} className="location-group">
              <div className="location-group-header">
                <span className="lg-dot" />
                {loc}
                <span className="lg-count">{entries.length}</span>
              </div>
              {entries.map(entry => (
                <div key={entry.id} className="memory-entry">
                  <img
                    className="memory-thumb"
                    src={entry.thumbnail}
                    alt={entry.location_label}
                    loading="lazy"
                    onClick={() => setLightbox(entry.thumbnail)}
                  />
                  <div className="memory-meta">
                    <p className="memory-desc">{entry.description}</p>
                    <div className="chips">
                      {entry.objects.slice(0, 4).map((o, i) => <span key={i} className="chip">{o}</span>)}
                      {entry.objects.length > 4 && (
                        <span className="chip chip-more">+{entry.objects.length - 4}</span>
                      )}
                    </div>
                    <div className="memory-time">{fmtRelative(entry.timestamp)}</div>
                  </div>
                  <button className="memory-delete" onClick={() => deleteEntry(entry.id)} title="Delete">
                    🗑
                  </button>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div className="lightbox" onClick={() => setLightbox(null)}>
          <img src={lightbox} alt="Memory frame" onClick={e => e.stopPropagation()} />
          <button className="lightbox-close" onClick={() => setLightbox(null)}>×</button>
        </div>
      )}

      {/* Debug */}
      <details className="debug">
        <summary>Debug</summary>
        <dl className="status">
          <div><dt>Secure</dt><dd>{secure ? "✅" : "❌"}</dd></div>
          <div><dt>WebSocket</dt><dd>{wsState}</dd></div>
          <div><dt>Frames</dt><dd>{framesSent}</dd></div>
          <div><dt>Last ack</dt><dd>{lastAck ? `#${lastAck.frame} · ${(lastAck.bytes / 1024).toFixed(1)} KB` : "—"}</dd></div>
          <div><dt>Voice</dt><dd>{liveState === "open" ? (talking ? "listening" : "ready") : "off"}</dd></div>
          <div><dt>Memories</dt><dd>{timeline.length}</dd></div>
          <div><dt>Flash</dt><dd>{flashCalls}/{flashBudget} calls</dd></div>
          <div><dt>Next scan</dt><dd>{scanning ? "now" : countdown > 0 ? `${countdown}s` : "ready"}</dd></div>
        </dl>
      </details>
    </div>
  );
}
