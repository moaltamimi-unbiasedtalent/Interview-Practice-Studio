import { describe, expect, it } from "vitest";
import { TurnMachine, canTransition } from "../state";

describe("TurnMachine", () => {
  it("allows the happy-path lifecycle", () => {
    const m = new TurnMachine();
    m.transitionTo("interviewer_speaking");
    m.transitionTo("candidate_thinking");
    m.transitionTo("candidate_speaking");
    m.transitionTo("processing_transcript");
    m.transitionTo("evaluating");
    m.transitionTo("ready_for_next");
    m.transitionTo("complete");
    expect(m.state).toBe("complete");
  });

  it("rejects an illegal transition", () => {
    const m = new TurnMachine();
    expect(() => m.transitionTo("evaluating")).toThrow();
  });

  it("interruption is only valid while the interviewer speaks", () => {
    const m = new TurnMachine();
    m.transitionTo("interviewer_speaking");
    m.interrupt();
    expect(m.state).toBe("candidate_speaking");
    expect(m.interrupted).toBe(true);
    expect(m.discardStaleAudio).toBe(true);
  });

  it("interruption from the wrong state throws", () => {
    const m = new TurnMachine();
    expect(() => m.interrupt()).toThrow();
  });

  it("error is reachable from any state", () => {
    const m = new TurnMachine();
    m.transitionTo("interviewer_speaking");
    m.transitionTo("error");
    expect(m.state).toBe("error");
    expect(canTransition("error", "preparing")).toBe(true);
  });
});
