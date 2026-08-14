// Pure turn state machine, mirrored from the Python backend so the frontend and
// backend agree on the live turn lifecycle. Kept free of DOM/audio/WebSocket so
// it can be unit-tested in isolation.

export type LiveTurnState =
  | "preparing"
  | "interviewer_speaking"
  | "candidate_thinking"
  | "candidate_speaking"
  | "processing_transcript"
  | "evaluating"
  | "ready_for_next"
  | "error"
  | "complete";

const ALLOWED: Record<LiveTurnState, LiveTurnState[]> = {
  preparing: ["interviewer_speaking", "error"],
  interviewer_speaking: ["candidate_thinking", "candidate_speaking", "error"],
  candidate_thinking: ["candidate_speaking", "complete", "error"],
  candidate_speaking: ["processing_transcript", "error"],
  processing_transcript: ["evaluating", "error"],
  evaluating: ["ready_for_next", "error"],
  ready_for_next: ["preparing", "complete", "error"],
  error: ["preparing", "complete"],
  complete: [],
};

export function canTransition(from: LiveTurnState, to: LiveTurnState): boolean {
  return ALLOWED[from]?.includes(to) ?? false;
}

export class TurnMachine {
  state: LiveTurnState = "preparing";
  interrupted = false;
  discardStaleAudio = false;

  transitionTo(next: LiveTurnState): void {
    // ERROR is always reachable (a failure can happen at any time).
    if (next !== "error" && !canTransition(this.state, next)) {
      throw new Error(`Illegal transition ${this.state} -> ${next}`);
    }
    this.state = next;
  }

  interrupt(): void {
    if (this.state !== "interviewer_speaking") {
      throw new Error("Interruption only valid while interviewer is speaking");
    }
    this.interrupted = true;
    this.discardStaleAudio = true;
    this.state = "candidate_speaking";
  }

  beginQuestion(): void {
    this.interrupted = false;
    this.discardStaleAudio = false;
    this.state = "preparing";
  }
}
