// Thin Gemini Live client wrapper. Connects with the ephemeral token only (the
// permanent key never reaches the browser) and exposes the events the UI needs.
// Handles generation-complete, interruption, GoAway and session-resumption
// signals, and surfaces close/error so the caller can apply a *bounded*
// reconnect policy.

import { GoogleGenAI, Modality } from "@google/genai";

export interface GeminiCallbacks {
  onInterviewerAudio: (pcm: ArrayBuffer) => void;
  onInterviewerText: (text: string) => void;
  onCandidateText: (text: string, isFinal: boolean) => void;
  onInterrupted: () => void; // model output was interrupted (barge-in)
  onGenerationComplete: () => void;
  onGoAway: (msSinceEpoch: number) => void;
  onResumptionUpdate: (handle: string) => void;
  onError: (message: string) => void;
  onClose: () => void;
}

export interface GeminiConfig {
  model: string;
  ephemeralToken: string;
  systemInstruction: string;
  resumptionHandle?: string;
}

export class GeminiLiveClient {
  private session: any = null;
  private ai: GoogleGenAI;
  private cfg: GeminiConfig;
  private cbs: GeminiCallbacks;

  constructor(cfg: GeminiConfig, cbs: GeminiCallbacks) {
    this.cfg = cfg;
    this.cbs = cbs;
    // The SDK authenticates with the short-lived token, not the permanent key.
    this.ai = new GoogleGenAI({ apiKey: cfg.ephemeralToken });
  }

  async connect(): Promise<void> {
    this.session = await this.ai.live.connect({
      model: this.cfg.model,
      config: {
        responseModalities: [Modality.AUDIO],
        systemInstruction: this.cfg.systemInstruction,
        // Server-side VAD with automatic interruption handling.
        realtimeInputConfig: { automaticActivityDetection: {} },
        inputAudioTranscription: {},
        outputAudioTranscription: {},
        sessionResumption: this.cfg.resumptionHandle
          ? { handle: this.cfg.resumptionHandle }
          : {},
        contextWindowCompression: { slidingWindow: {} },
      },
      callbacks: {
        onmessage: (msg: any) => this.handleMessage(msg),
        onerror: (e: any) => this.cbs.onError(String(e?.message ?? "live error")),
        onclose: () => this.cbs.onClose(),
      },
    });
  }

  private handleMessage(msg: any): void {
    if (msg.serverContent?.interrupted) this.cbs.onInterrupted();
    const parts = msg.serverContent?.modelTurn?.parts ?? [];
    for (const part of parts) {
      if (part.inlineData?.data) {
        this.cbs.onInterviewerAudio(base64ToArrayBuffer(part.inlineData.data));
      }
      if (part.text) this.cbs.onInterviewerText(part.text);
    }
    if (msg.serverContent?.outputTranscription?.text) {
      this.cbs.onInterviewerText(msg.serverContent.outputTranscription.text);
    }
    if (msg.serverContent?.inputTranscription?.text) {
      this.cbs.onCandidateText(
        msg.serverContent.inputTranscription.text,
        Boolean(msg.serverContent.turnComplete),
      );
    }
    if (msg.serverContent?.generationComplete) this.cbs.onGenerationComplete();
    if (msg.sessionResumptionUpdate?.resumable && msg.sessionResumptionUpdate.newHandle) {
      this.cbs.onResumptionUpdate(msg.sessionResumptionUpdate.newHandle);
    }
    if (msg.goAway?.timeLeft) this.cbs.onGoAway(Date.now() + toMillis(msg.goAway.timeLeft));
  }

  sendAudioChunk(pcm16: ArrayBuffer): void {
    if (!this.session) return;
    this.session.sendRealtimeInput({
      audio: { data: arrayBufferToBase64(pcm16), mimeType: "audio/pcm;rate=16000" },
    });
  }

  // Ask the interviewer to speak a specific canonical question (authored by
  // OpenRouter). Gemini only voices it — it does not invent questions. Current
  // Live API: deliver the instruction via sendRealtimeInput({text}) rather than
  // the older sendClientContent turn flow.
  speakQuestion(question: string): void {
    if (!this.session) return;
    this.session.sendRealtimeInput({
      text: `Ask the candidate exactly this question, verbatim: ${question}`,
    });
  }

  close(): void {
    try {
      this.session?.close?.();
    } finally {
      this.session = null;
    }
  }
}

function toMillis(duration: string): number {
  const seconds = parseFloat(String(duration).replace("s", ""));
  return Number.isFinite(seconds) ? seconds * 1000 : 0;
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}
