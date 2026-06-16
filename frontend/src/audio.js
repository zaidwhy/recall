// Audio helpers for the Gemini Live voice round-trip.
// Capture: Float32 @ device rate -> resample to 16 kHz -> Int16 (sent to backend).
// Playback: Int16 @ 24 kHz from Gemini -> Float32 -> scheduled on an AudioContext.

export function downsampleTo16k(f32, inRate) {
  const outRate = 16000;
  if (inRate === outRate) return f32;
  const ratio = inRate / outRate;
  const outLen = Math.round(f32.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const idx = i * ratio;
    const i0 = Math.floor(idx);
    const i1 = Math.min(i0 + 1, f32.length - 1);
    const frac = idx - i0;
    out[i] = f32[i0] * (1 - frac) + f32[i1] * frac;
  }
  return out;
}

export function f32ToInt16(f32) {
  const i16 = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return i16;
}

function int16ToF32(i16) {
  const f32 = new Float32Array(i16.length);
  for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 0x8000;
  return f32;
}

// Schedules PCM chunks back-to-back so playback is gapless.
export class AudioPlayer {
  constructor(sampleRate = 24000) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new Ctx({ sampleRate });
    this.rate = sampleRate;
    this.head = 0;
  }

  async resume() {
    if (this.ctx.state !== "running") await this.ctx.resume();
  }

  playInt16(arrayBuffer) {
    const i16 = new Int16Array(arrayBuffer);
    if (!i16.length) return;
    const f32 = int16ToF32(i16);
    const buf = this.ctx.createBuffer(1, f32.length, this.rate);
    buf.copyToChannel(f32, 0);
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    const t = Math.max(this.ctx.currentTime + 0.02, this.head);
    src.start(t);
    this.head = t + buf.duration;
  }

  close() {
    try {
      this.ctx.close();
    } catch {
      /* ignore */
    }
  }
}
