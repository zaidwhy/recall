// AudioWorklet that batches mic samples and posts them to the main thread.
// Runs at the capture AudioContext's sample rate; the main thread resamples to 16 kHz.
class PCMCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this._chunks = [];
    this._count = 0;
    this._threshold = 2048; // ~43ms @ 48k, ~128ms @ 16k — keeps WS messages chunky
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input[0]) {
      this._chunks.push(input[0].slice(0));
      this._count += input[0].length;
      if (this._count >= this._threshold) {
        const out = new Float32Array(this._count);
        let offset = 0;
        for (const c of this._chunks) {
          out.set(c, offset);
          offset += c.length;
        }
        this.port.postMessage(out, [out.buffer]);
        this._chunks = [];
        this._count = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PCMCapture);
