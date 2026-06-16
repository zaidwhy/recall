import { useCallback, useEffect, useRef, useState } from "react";

const CAPTURE_INTERVAL_MS = 2000; // Week 1: gentle sampling, just proving the pipe
const JPEG_QUALITY = 0.6;
const MAX_WIDTH = 640; // downscale before sending — keeps frames small over the tunnel

// Derive the WebSocket URL from the page origin so it becomes wss:// through the
// cloudflared tunnel automatically (no hardcoded LAN IP, no mixed-content).
function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

export default function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const streamRef = useRef(null);

  const [running, setRunning] = useState(false);
  const [wsState, setWsState] = useState("idle"); // idle | connecting | open | closed
  const [framesSent, setFramesSent] = useState(0);
  const [lastAck, setLastAck] = useState(null);
  const [error, setError] = useState("");
  const [observation, setObservation] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    if (wsRef.current) wsRef.current.close();
    wsRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setRunning(false);
    setWsState("closed");
  }, []);

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

  // Must be triggered by a user gesture (iOS Safari blocks camera/autoplay otherwise).
  const start = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" }, // rear camera
        audio: true,
      });
      streamRef.current = stream;
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play();

      setWsState("connecting");
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      ws.onopen = () => {
        setWsState("open");
        setRunning(true);
        timerRef.current = setInterval(captureFrame, CAPTURE_INTERVAL_MS);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "ack") setLastAck(msg);
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => setWsState("closed");
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
        <p className="tag">your phone is the camera · Week 1 capture test</p>
      </header>

      {!secure && (
        <div className="warn">
          ⚠ Not a secure context. The camera will fail over a plain LAN IP — open the
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
          <button className="danger" onClick={stop}>
            Stop
          </button>
        )}
      </div>

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
      </dl>

      {error && <div className="error">{error}</div>}
    </div>
  );
}
