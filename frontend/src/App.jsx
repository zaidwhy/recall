import { useCallback, useEffect, useRef, useState } from "react";
import { AudioPlayer, downsampleTo16k, f32ToInt16 } from "./audio.js";

const CAPTURE_INTERVAL_MS = 2000;
const JPEG_QUALITY = 0.6;
const MAX_WIDTH = 640;
const NARRATE_TIMEOUT_MS = 7000; // auto-stop after 7 s in tap-to-ask mode

function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const streamRef = useRef(null);

  // voice refs
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

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    teardownVoice();
    if (wsRef.current) wsRef.current.close();
    wsRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setRunning(false);
    setWsState("closed");
    setRecording(false);
  }, [teardownVoice]);

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

  const captureFrame = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const dataUrl = grabFrame();
    if (!dataUrl) return;
    ws.send(JSON.stringify({ type: "frame", ts: Date.now(), data: dataUrl }));
    setFramesSent((n) => n + 1);
  }, [grabFrame]);

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
    setTimeline((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const startVoice = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("Start the camera first — it opens the connection.");
      return;
    }
    if (!streamRef.current) {
      setError("No microphone stream. Restart the camera (grants mic too).");
      return;
    }
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
        const i16 = f32ToInt16(downsampleTo16k(e.data, micCtx.sampleRate));
        w.send(i16.buffer);
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

  // Tap-to-ask: single tap starts, auto-stops after NARRATE_TIMEOUT_MS, or tap again to stop early.
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
      await video.play();

      setWsState("connecting");
      const ws = new WebSocket(wsUrl());
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onopen = () => {
        setWsState("open");
        setRunning(true);
        timerRef.current = setInterval(captureFrame, CAPTURE_INTERVAL_MS);
        fetch("/memory")
          .then((r) => r.json())
          .then((entries) => {
            setTimeline(entries.map((e) => ({ ...e, thumbnail: `/thumbnails/${e.id}.jpg` })));
          })
          .catch(() => {});
      };
      ws.onmessage = (ev) => {
        if (ev.data instanceof ArrayBuffer) {
          playerRef.current?.playInt16(ev.data);
          return;
        }
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "ack") {
            setLastAck(msg);
          } else if (msg.type === "observation") {
            setObservation(msg);
            setAnalyzing(false);
          } else if (msg.type === "ingested") {
            setTimeline((prev) => [{
              id: msg.id,
              thumbnail: msg.thumbnail,
              location_label: msg.location_label,
              description: msg.description,
              objects: msg.objects,
              timestamp: msg.timestamp,
            }, ...prev]);
            setIngestCount((n) => n + 1);
          } else if (msg.type === "record_status") {
            setRecording(msg.recording);
          } else if (msg.type === "transcript") {
            if (msg.role === "user") setUserText((t) => t + msg.text);
            else setAssistantText((t) => t + msg.text);
          } else if (msg.type === "recalled") {
            setRecalled(msg.match);
          } else if (msg.type === "live_status") {
            setLiveState(msg.state === "open" ? "open" : "idle");
          } else if (msg.type === "error") {
            setError(msg.detail || "server error");
            setAnalyzing(false);
          }
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        setWsState("closed");
        setLiveState("idle");
        setRecording(false);
      };
      ws.onerror = () => setError("WebSocket error — is the backend running on this origin?");
    } catch (e) {
      setError(
        e?.name === "NotAllowedError"
          ? "Camera/mic permission denied. Grant access and retry."
          : `Could not start camera: ${e?.message || e}. (Needs HTTPS — use the tunnel URL.)`
      );
      stop();
    }
  }, [captureFrame, stop]);

  useEffect(() => () => stop(), [stop]);

  const secure = window.isSecureContext;

  return (
    <div className="app">
      <header>
        <h1>Recall</h1>
        <p className="tag">see once · remember always</p>
      </header>

      {!secure && (
        <div className="warn">
          Not a secure context — camera will fail over a plain LAN IP.
          Open the <code>https://*.trycloudflare.com</code> tunnel URL instead.
        </div>
      )}

      <div className="stage">
        <video ref={videoRef} playsInline autoPlay muted />
        <canvas ref={canvasRef} hidden />
        {running && recording && (
          <div className="recording-pill">
            <span className="rec-dot" /> REC · {ingestCount} {ingestCount === 1 ? "scene" : "scenes"}
          </div>
        )}
      </div>

      <div className="controls">
        {!running ? (
          <button className="primary" onClick={start}>Start camera</button>
        ) : (
          <>
            <button
              className={recording ? "record recording" : "record"}
              onClick={toggleRecord}
            >
              {recording ? "⏹ Stop" : "⏺ Record"}
            </button>
            <button className="ghost small" onClick={analyzeFrame} disabled={analyzing}>
              {analyzing ? "…" : "Analyze"}
            </button>
            <button className="danger small" onClick={stop}>End</button>
          </>
        )}
      </div>

      {running && (
        <div className="voice">
          {liveState === "idle" ? (
            <button className="voice-start" onClick={startVoice}>
              🎙 Enable voice
            </button>
          ) : (
            <div className="ptt-area">
              <button
                className={`ptt${talking ? " ptt--active" : ""}`}
                onPointerDown={startTalk}
                onPointerUp={stopTalk}
                onPointerLeave={stopTalk}
                onContextMenu={(e) => e.preventDefault()}
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

      {(userText || assistantText) && (
        <div className="transcript">
          {userText && <p className="t-you">"{userText}"</p>}
          {assistantText && <p className="t-recall">{assistantText}</p>}
        </div>
      )}

      {recalled && (
        <div className="recalled">
          <div className="recalled-badge">
            🧠 Remembered
            <button className="recalled-x" onClick={() => setRecalled(null)}>×</button>
          </div>
          <div className="memory-entry">
            <img className="memory-thumb" src={recalled.thumbnail} alt={recalled.location_label} />
            <div className="memory-meta">
              <div className="memory-loc">📍 {recalled.location_label}</div>
              <p className="memory-desc">{recalled.description}</p>
              <div className="chips">
                {recalled.objects.map((o, i) => <span key={i} className="chip">{o}</span>)}
              </div>
              <div className="memory-time">~{recalled.minutes_ago} min ago</div>
            </div>
          </div>
        </div>
      )}

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

      {timeline.length > 0 && (
        <div className="timeline">
          <h2 className="timeline-heading">Memory · {timeline.length}</h2>
          {timeline.map((entry) => (
            <div key={entry.id} className="memory-entry">
              <img
                className="memory-thumb"
                src={entry.thumbnail}
                alt={entry.location_label}
                loading="lazy"
              />
              <div className="memory-meta">
                <div className="memory-loc">📍 {entry.location_label}</div>
                <p className="memory-desc">{entry.description}</p>
                <div className="chips">
                  {entry.objects.map((o, i) => <span key={i} className="chip">{o}</span>)}
                </div>
                <div className="memory-time">{fmtTime(entry.timestamp)}</div>
              </div>
              <button
                className="memory-delete"
                onClick={() => deleteEntry(entry.id)}
                title="Delete"
              >🗑</button>
            </div>
          ))}
        </div>
      )}

      <details className="debug">
        <summary>Debug</summary>
        <dl className="status">
          <div><dt>Secure</dt><dd>{secure ? "✅" : "❌"}</dd></div>
          <div><dt>WebSocket</dt><dd>{wsState}</dd></div>
          <div><dt>Frames</dt><dd>{framesSent}</dd></div>
          <div><dt>Last ack</dt><dd>{lastAck ? `#${lastAck.frame} · ${(lastAck.bytes / 1024).toFixed(1)} KB` : "—"}</dd></div>
          <div><dt>Voice</dt><dd>{liveState === "open" ? (talking ? "listening" : "ready") : "off"}</dd></div>
          <div><dt>Memories</dt><dd>{timeline.length}</dd></div>
        </dl>
      </details>
    </div>
  );
}
