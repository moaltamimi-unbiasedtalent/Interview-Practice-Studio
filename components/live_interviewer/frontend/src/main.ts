// Streamlit component glue: wires the audio pipeline, the Gemini Live client and
// the turn state machine, and reports events back to Python via
// Streamlit.setComponentValue. Interview intelligence stays in Python/OpenRouter;
// this file only handles the real-time interface.

import { Streamlit, RenderData } from "streamlit-component-lib";
import { GeminiLiveClient } from "./gemini";
import { TurnMachine, LiveTurnState } from "./state";

interface SessionConfig {
  model: string;
  ephemeral_token: string;
  token_expires_at: number;
  input_sample_rate: number;
  output_sample_rate: number;
  chunk_ms: number;
  max_reconnects: number;
  question?: string; // canonical question (authored by OpenRouter)
  system_instruction?: string;
}

const machine = new TurnMachine();
let client: GeminiLiveClient | null = null;
let audioContext: AudioContext | null = null;
let micStream: MediaStream | null = null;
let workletNode: AudioWorkletNode | null = null;
let playbackQueue: AudioBufferSourceNode[] = [];
let reconnects = 0;
let muted = false;
let candidateTranscript = "";
let resumptionHandle: string | undefined;
let currentConfig: SessionConfig | null = null;

const root = document.getElementById("root")!;
const statusEl = document.createElement("div");
const transcriptEl = document.createElement("div");
root.append(statusEl, transcriptEl);

function report(extra: Record<string, unknown> = {}): void {
  Streamlit.setComponentValue({
    state: machine.state,
    interrupted: machine.interrupted,
    candidate_transcript: candidateTranscript,
    reconnects,
    muted,
    ...extra,
  });
}

function setStatus(text: string): void {
  statusEl.textContent = `Status: ${text}`;
}

function setState(next: LiveTurnState): void {
  machine.transitionTo(next);
  setStatus(next);
  report();
}

function stopInterviewerAudio(): void {
  // Discard any queued interviewer audio so the two streams never overlap.
  for (const node of playbackQueue) {
    try {
      node.stop();
    } catch {
      /* already stopped */
    }
  }
  playbackQueue = [];
}

async function startMic(sampleRate: number, chunkMs: number): Promise<void> {
  micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new AudioContext();
  await audioContext.audioWorklet.addModule("./pcm-worklet.js");
  const source = audioContext.createMediaStreamSource(micStream);
  workletNode = new AudioWorkletNode(audioContext, "pcm-worklet", {
    processorOptions: { targetRate: sampleRate, chunkMs },
  });
  workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    if (muted || !client) return;
    client.sendAudioChunk(event.data);
    // Barge-in: the candidate started talking while the interviewer was speaking.
    if (machine.state === "interviewer_speaking") {
      machine.interrupt();
      stopInterviewerAudio();
      setStatus("candidate_speaking");
      report({ discard_stale_audio: true });
    }
  };
  source.connect(workletNode);
}

function playInterviewerAudio(pcm: ArrayBuffer, outRate: number): void {
  if (!audioContext) return;
  const int16 = new Int16Array(pcm);
  const buffer = audioContext.createBuffer(1, int16.length, outRate);
  const channel = buffer.getChannelData(0);
  for (let i = 0; i < int16.length; i++) channel[i] = int16[i] / 0x8000;
  const node = audioContext.createBufferSource();
  node.buffer = buffer;
  node.connect(audioContext.destination);
  node.onended = () => {
    playbackQueue = playbackQueue.filter((n) => n !== node);
  };
  playbackQueue.push(node);
  node.start();
}

async function connect(cfg: SessionConfig): Promise<void> {
  client = new GeminiLiveClient(
    {
      model: cfg.model,
      ephemeralToken: cfg.ephemeral_token,
      systemInstruction:
        cfg.system_instruction ??
        "You are a professional interviewer. Speak only the exact question you " +
          "are given. Keep acknowledgements brief (e.g. 'Thank you.'). Never " +
          "invent new questions or change the interview's direction.",
      resumptionHandle,
    },
    {
      onInterviewerAudio: (pcm) => playInterviewerAudio(pcm, cfg.output_sample_rate),
      onInterviewerText: () => report(),
      onCandidateText: (text, isFinal) => {
        candidateTranscript = text;
        if (isFinal) report({ transcript_final: true });
        else report();
      },
      onInterrupted: () => stopInterviewerAudio(),
      onGenerationComplete: () => {
        if (machine.state === "interviewer_speaking") setState("candidate_thinking");
      },
      onGoAway: () => scheduleReconnect(cfg),
      onResumptionUpdate: (handle) => (resumptionHandle = handle),
      onError: (message) => {
        setStatus(`error: ${message}`);
        machine.state = "error";
        report({ error: message });
        scheduleReconnect(cfg);
      },
      onClose: () => scheduleReconnect(cfg),
    },
  );
  await client.connect();
  reconnects = 0;
}

function scheduleReconnect(cfg: SessionConfig): void {
  if (reconnects >= cfg.max_reconnects) {
    setStatus("error: gave up after max reconnects");
    machine.state = "error";
    report({ fatal: true });
    return; // bounded — never an infinite loop
  }
  reconnects += 1;
  const delay = Math.min(1000 * 2 ** (reconnects - 1), 8000);
  setStatus(`reconnecting (${reconnects}/${cfg.max_reconnects})`);
  report();
  window.setTimeout(() => connect(cfg).catch(() => scheduleReconnect(cfg)), delay);
}

async function begin(cfg: SessionConfig): Promise<void> {
  currentConfig = cfg;
  try {
    setStatus("preparing");
    await startMic(cfg.input_sample_rate, cfg.chunk_ms);
    await connect(cfg);
    if (cfg.question) {
      client?.speakQuestion(cfg.question);
      setState("interviewer_speaking");
    }
  } catch (err) {
    setStatus(`error: ${(err as Error).message}`);
    machine.state = "error";
    report({ error: (err as Error).message });
  }
}

function cleanup(): void {
  stopInterviewerAudio();
  workletNode?.disconnect();
  micStream?.getTracks().forEach((t) => t.stop());
  audioContext?.close();
  client?.close();
  workletNode = null;
  micStream = null;
  audioContext = null;
  client = null;
}

function onRender(event: Event): void {
  const data = (event as CustomEvent<RenderData>).detail;
  const cfg = data.args["session_config"] as SessionConfig;
  if (!currentConfig) begin(cfg);
  Streamlit.setFrameHeight();
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
Streamlit.setFrameHeight();
window.addEventListener("beforeunload", cleanup);

export { cleanup };
