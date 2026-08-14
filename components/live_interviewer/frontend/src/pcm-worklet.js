// AudioWorklet that downsamples the mic stream to 16 kHz mono and emits small
// low-latency PCM16 chunks (~30 ms) rather than buffering seconds of audio.
class PcmWorklet extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.targetRate = opts.targetRate || 16000;
    this.chunkMs = opts.chunkMs || 30;
    this.chunkSamples = Math.round((this.targetRate * this.chunkMs) / 1000);
    this._acc = [];
    this._accLen = 0;
    this._ratio = sampleRate / this.targetRate; // sampleRate is the worklet global
    this._pos = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];
    // Linear-interpolation resample to the target rate.
    for (let i = this._pos; i < channel.length; i += this._ratio) {
      const idx = Math.floor(i);
      const sample = channel[idx] || 0;
      const clamped = Math.max(-1, Math.min(1, sample));
      this._acc.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff);
      this._accLen += 1;
      if (this._accLen >= this.chunkSamples) {
        const buffer = new Int16Array(this._acc);
        this.port.postMessage(buffer.buffer, [buffer.buffer]);
        this._acc = [];
        this._accLen = 0;
      }
    }
    this._pos = (this._pos + channel.length) % 1 === 0 ? 0 : this._pos; // reset
    this._pos = 0;
    return true;
  }
}

registerProcessor("pcm-worklet", PcmWorklet);
