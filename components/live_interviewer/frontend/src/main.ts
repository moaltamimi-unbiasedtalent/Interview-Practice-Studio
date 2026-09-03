// Streamlit component glue: wires the audio pipeline, the Gemini Live client and
// the turn state machine, and reports events back to Python via
// Streamlit.setComponentValue. Interview intelligence stays in Python/OpenRouter;
// this file only handles the real-time interface. Lifecycle policy (session
// identity, token expiry, bounded reconnect) lives in the unit-tested
// ./lifecycle module; barge-in is driven by the provider's interruption event,
// never by the mere presence of microphone audio.

import { Streamlit, RenderData } from "streamlit-component-lib";
import { GeminiLiveClient } from "./gemini";
import { TurnMachine, LiveTurnState } from "./state";
import {
  LiveConfig,
  ReconnectController,
  isTokenExpired,
  sessionIdentity,
} from "./lifecycle";

const machine = new TurnMachine();
let client: GeminiLiveClient | null = null;
let audioContext: AudioContext | null = null;
let micStream: MediaStream | null = null;
let workletNode: AudioWorkletNode | null = null;
let playbackQueue: AudioBufferSourceNode[] = [];
let reconnect: ReconnectController | null = null;
let muted = false;
let candidateTranscript = "";
let resumptionHandle: string | undefined;
let currentIdentity: string | null = null;

const root = document.getElementById("root")!;
const statusEl = document.createElement("div");
const transcriptEl = document.createElement("div");
root.append(statusEl, transcriptEl);

function report(extra: Record<string, unknown> = {}): void {
  Streamlit.setComponentValue({
    state: machine.state,
    interrupted: machine.interrupted,
    candidate_transcript: candidateTranscript,
    reconnects: reconnect?.attempts ?? 0,
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

// Authoritative barge-in: the provider's server-side VAD reports a real
// interruption. Guarded by state so it fires at most once per interviewer turn.
function onProviderInterrupted(): void {
  stopInterviewerAudio();
  if (machine.onProviderInterrupt()) {
    // → candidate_speaking (fires at most once per interviewer turn)
    setStatus("candidate_speaking");
    report({ discard_stale_audio: true });
  }
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
    // Forward audio only. Mere PCM presence (silence, room noise, a continuous
    // stream) must NOT interrupt the interviewer — barge-in comes from the
    // provider's interruption event (onProviderInterrupted).
    if (muted || !client) return;
    client.sendAudioChunk(event.data);
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

async function connect(cfg: LiveConfig): Promise<void> {
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
      onInterrupted: onProviderInterrupted,
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
  reconnect?.onConnected(); // cancel any pending retry; KEEP the attempt budget
}

function enterNeedsTokenRefresh(): void {
  // Controlled state: the token is gone. Do not connect/reconnect; wait for
  // Python to mint a fresh token (a new config identity restarts the session).
  stopInterviewerAudio();
  setStatus("Session expired — waiting for a refreshed session.");
  machine.state = "error";
  report({ needs_token_refresh: true });
}

function scheduleReconnect(cfg: LiveConfig): void {
  if (!reconnect) return;
  const outcome = reconnect.schedule(
    () => connect(cfg).catch(() => scheduleReconnect(cfg)),
    { tokenExpired: isTokenExpired(cfg, Date.now()) },
  );
  if (outcome === "token_expired") {
    enterNeedsTokenRefresh();
  } else if (outcome === "exhausted") {
    setStatus("error: gave up after max reconnects");
    machine.state = "error";
    report({ fatal: true });
  } else if (outcome === "scheduled") {
    setStatus(`reconnecting (${reconnect.attempts}/${cfg.max_reconnects})`);
    report();
  }
  // "already_pending" / "stopped": no-op (one timer maximum).
}

async function begin(cfg: LiveConfig): Promise<void> {
  currentIdentity = sessionIdentity(cfg);
  reconnect = new ReconnectController(cfg.max_reconnects); // fresh budget per session
  // Never open a session with an already-expired ephemeral token.
  if (isTokenExpired(cfg, Date.now())) {
    enterNeedsTokenRefresh();
    return;
  }
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
  reconnect?.stop(); // cancel any pending reconnect timer
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

// Restart the Live session for a genuinely new config (new question / refreshed
// token / changed settings). Exactly one controlled teardown + start.
function restart(cfg: LiveConfig): void {
  cleanup();
  machine.beginQuestion(); // reset turn state for the new session
  begin(cfg);
}

function onRender(event: Event): void {
  const data = (event as CustomEvent<RenderData>).detail;
  const cfg = data.args["session_config"] as LiveConfig;
  const identity = sessionIdentity(cfg);
  if (currentIdentity === null) {
    begin(cfg); // first render
  } else if (identity !== currentIdentity) {
    restart(cfg); // materially-changed config → one controlled restart
  }
  // Unchanged effective config on an unrelated rerender → no restart.
  Streamlit.setFrameHeight();
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
Streamlit.setFrameHeight();
window.addEventListener("beforeunload", cleanup);

export { cleanup };
