import { useCallback, useEffect, useRef, useState } from "react";
import { AudioPlayer, downsampleTo16k, f32ToInt16 } from "./audio.js";

const CAPTURE_INTERVAL_MS = 2000;
const JPEG_QUALITY = 0.6;
const MAX_WIDTH = 640;

function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const streamRef = useRef(null);

  // voice (Gemini Live) refs
  const micCtxRef = useRef(null);
  const workletRef = useRef(null);
  const micSourceRef = useRef(null);
  const playerRef = useRef(null);
  const talkingRef = useRef(false);

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

  // Week 2: memory
  const [recording, setRecording] = useState(false);
  const [timeline, setTimeline] = useState([]);
  const [ingestCount, setIngestCount] = useState(0);

  // Week 3: spotlight card for the last recalled frame
  const [recalled, setRecalled] = useState(null);

  const teardownVoice = useCallback(() => {
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
    if (recording) {
      ws.send(JSON.stringify({ type: "record_stop" }));
    } else {
      ws.send(JSON.stringify({ type: "record_start" }));
    }
  }, [recording]);

  const deleteEntry = useCallback(async (id) => {
    try {
      await fetch(`/memory/${id}`, { method: "DELETE" });
    } catch { /* ignore */ }
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
    talkingRef.current = true;
    setTalking(true);
    ws.send(JSON.stringify({ type: "talk_start" }));
  }, []);

  const stopTalk = useCallback(() => {
    if (!talkingRef.current) return;
    talkingRef.current = false;
    setTalking(false);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "talk_end" }));
    }
  }, []);

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
        // Fetch existing memory timeline
        fetch("/memory")
          .then((r) => r.json())
          .then((entries) => {
            setTimeline(entries.map((e) => ({
              ...e,
              thumbnail: `/thumbnails/${e.id}.jpg`,
            })));
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
        } catch {
          /* ignore */
        }
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
          : `Could not start camera: ${e?.message || e}. (Camera needs HTTPS — use the tunnel URL, not a LAN IP.)`
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
        <p className="tag">your phone is the camera · vision + voice + memory</p>
      </header>

      {!secure && (
        <div className="warn">
          Not a secure context. The camera will fail over a plain LAN IP — open the
          <code> https://*.trycloudflare.com </code> tunnel URL instead.
        </div>
      )}

      <div className="stage">
        <video ref={videoRef} playsInline autoPlay muted />
        <canvas ref={canvasRef} hidden />
      </div>

      <div className="controls">
        {!running ? (
          <button className="primary" onClick={start}>
            Start camera
          </button>
        ) : (
          <>
            <button className="primary" onClick={analyzeFrame} disabled={analyzing}>
              {analyzing ? "Analyzing…" : "What am I looking at?"}
            </button>
            <button
              className={recording ? "record recording" : "record"}
              onClick={toggleRecord}
            >
              {recording ? "⏹ Stop recording" : "⏺ Record memory"}
            </button>
            <button className="danger" onClick={stop}>
              Stop
            </button>
          </>
        )}
      </div>

      {running && recording && (
        <div className="ingest-status">
          Memorizing… {ingestCount > 0 ? `${ingestCount} scene${ingestCount === 1 ? "" : "s"} stored` : "watching for changes"}
        </div>
      )}

      {running && (
        <div className="voice">
          {liveState === "idle" ? (
            <button className="ghost" onClick={startVoice}>
              🎙 Start voice
            </button>
          ) : (
            <>
              <button
                className={talking ? "talk talking" : "talk"}
                onPointerDown={startTalk}
                onPointerUp={stopTalk}
                onPointerLeave={stopTalk}
                onContextMenu={(e) => e.preventDefault()}
              >
                {talking ? "🔴 Listening… (release to send)" : "🎤 Hold to talk"}
              </button>
              <button className="ghost" onClick={endVoice}>
                End voice
              </button>
            </>
          )}
          {(userText || assistantText) && (
            <div className="caption">
              {userText && <p className="you">You: {userText}</p>}
              {assistantText && <p className="recall">Recall: {assistantText}</p>}
            </div>
          )}
        </div>
      )}

      {observation && (
        <div className="observation">
          <div className="loc">📍 {observation.location_label}</div>
          <p className="desc">{observation.description}</p>
          <div className="chips">
            {observation.objects.map((o, i) => (
              <span key={i} className="chip">{o}</span>
            ))}
          </div>
          <div className="latency">Gemini Flash · {observation.latency_ms} ms</div>
        </div>
      )}

      <dl className="status">
        <div>
          <dt>Secure context</dt>
          <dd>{secure ? "✅ yes" : "❌ no"}</dd>
        </div>
        <div>
          <dt>WebSocket</dt>
          <dd>{wsState}</dd>
        </div>
        <div>
          <dt>Frames sent</dt>
          <dd>{framesSent}</dd>
        </div>
        <div>
          <dt>Last ack</dt>
          <dd>{lastAck ? `#${lastAck.frame} · ${(lastAck.bytes / 1024).toFixed(1)} KB` : "—"}</dd>
        </div>
        <div>
          <dt>Voice</dt>
          <dd>{liveState === "open" ? (talking ? "listening" : "ready") : "off"}</dd>
        </div>
        <div>
          <dt>Memories</dt>
          <dd>{timeline.length}</dd>
        </div>
      </dl>

      {error && <div className="error">{error}</div>}

      {timeline.length > 0 && (
        <div className="timeline">
          <h2 className="timeline-heading">Memory timeline</h2>
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
                  {entry.objects.map((o, i) => (
                    <span key={i} className="chip">{o}</span>
                  ))}
                </div>
                <div className="memory-time">{fmtTime(entry.timestamp)}</div>
              </div>
              <button
                className="memory-delete"
                onClick={() => deleteEntry(entry.id)}
                title="Delete"
              >
                🗑
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
