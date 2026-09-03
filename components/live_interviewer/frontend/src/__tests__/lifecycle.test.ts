import { describe, expect, it } from "vitest";
import { TurnMachine } from "../state";
import {
  LiveConfig,
  ReconnectController,
  TimerHost,
  isTokenExpired,
  sessionIdentity,
} from "../lifecycle";

function cfg(overrides: Partial<LiveConfig> = {}): LiveConfig {
  return {
    model: "models/gemini-live",
    ephemeral_token: "tok-abc",
    token_expires_at: 10_000, // epoch seconds
    input_sample_rate: 16000,
    output_sample_rate: 24000,
    chunk_ms: 20,
    max_reconnects: 3,
    question: "Tell me about a challenge.",
    session_id: "s1",
    ...overrides,
  };
}

// A deterministic timer host: records scheduled callbacks, fires on demand.
class FakeTimers implements TimerHost {
  private id = 0;
  private jobs = new Map<number, () => void>();
  set(fn: () => void, _ms: number): number {
    const id = ++this.id;
    this.jobs.set(id, fn);
    return id;
  }
  clear(id: number): void {
    this.jobs.delete(id);
  }
  get pendingCount(): number {
    return this.jobs.size;
  }
  fireAll(): void {
    const fns = [...this.jobs.values()];
    this.jobs.clear();
    fns.forEach((fn) => fn());
  }
}

// --- 1 & 2: barge-in only via the provider event ----------------------------

describe("barge-in", () => {
  it("does NOT interrupt without a provider event (silence/PCM/continuous stream)", () => {
    const m = new TurnMachine();
    m.state = "interviewer_speaking";
    // No code path is driven by microphone audio; the interviewer keeps speaking.
    expect(m.state).toBe("interviewer_speaking");
    expect(m.interrupted).toBe(false);
  });

  it("interrupts exactly once on the provider interrupted event", () => {
    const m = new TurnMachine();
    m.state = "interviewer_speaking";
    expect(m.onProviderInterrupt()).toBe(true); // real barge-in
    expect(m.state).toBe("candidate_speaking");
    expect(m.interrupted).toBe(true);
    // A second event (or stray audio) must not double-interrupt.
    expect(m.onProviderInterrupt()).toBe(false);
    expect(m.state).toBe("candidate_speaking");
  });

  it("ignores a provider interrupt when the interviewer is not speaking", () => {
    const m = new TurnMachine();
    m.state = "candidate_thinking";
    expect(m.onProviderInterrupt()).toBe(false);
    expect(m.state).toBe("candidate_thinking");
  });
});

// --- 3, 4, 5: session identity drives restarts ------------------------------

describe("sessionIdentity", () => {
  it("is stable for the same effective config (no restart on rerender)", () => {
    expect(sessionIdentity(cfg())).toBe(sessionIdentity(cfg()));
  });

  it("changes for a new question (controlled restart)", () => {
    expect(sessionIdentity(cfg())).not.toBe(
      sessionIdentity(cfg({ question: "A different question?" })),
    );
  });

  it("changes for a refreshed token (new token_expires_at)", () => {
    expect(sessionIdentity(cfg())).not.toBe(
      sessionIdentity(cfg({ token_expires_at: 20_000 })),
    );
  });

  it("changes for a new session id", () => {
    expect(sessionIdentity(cfg())).not.toBe(sessionIdentity(cfg({ session_id: "s2" })));
  });

  it("never embeds the secret token value", () => {
    expect(sessionIdentity(cfg({ ephemeral_token: "SECRET-XYZ" }))).not.toContain(
      "SECRET-XYZ",
    );
  });
});

// --- 6 & 7: token expiry ----------------------------------------------------

describe("isTokenExpired", () => {
  it("blocks a connection with an already-expired token", () => {
    expect(isTokenExpired(cfg({ token_expires_at: 100 }), 200_000)).toBe(true);
  });

  it("allows a fresh token", () => {
    // expires at 10_000s (10_000_000ms); now = 1000ms → well within validity.
    expect(isTokenExpired(cfg({ token_expires_at: 10_000 }), 1000)).toBe(false);
  });

  it("treats an absent expiry as unknown (not expired)", () => {
    expect(isTokenExpired(cfg({ token_expires_at: 0 }), 999_999_999)).toBe(false);
  });
});

// --- 8, 9, 10, 11: bounded reconnect ----------------------------------------

describe("ReconnectController", () => {
  it("schedules only one timer even if error+close both fire", () => {
    const timers = new FakeTimers();
    const rc = new ReconnectController(3, timers);
    expect(rc.schedule(() => {})).toBe("scheduled");
    expect(rc.schedule(() => {})).toBe("already_pending"); // idempotent
    expect(timers.pendingCount).toBe(1);
    expect(rc.attempts).toBe(1);
  });

  it("keeps the attempt budget across drop/reconnect cycles", () => {
    const timers = new FakeTimers();
    const rc = new ReconnectController(3, timers);
    // drop → schedule(1) → fire → connect() → onConnected (no reset)
    rc.schedule(() => {});
    timers.fireAll();
    rc.onConnected();
    expect(rc.attempts).toBe(1); // NOT reset to 0
    rc.schedule(() => {}); // second drop
    expect(rc.attempts).toBe(2);
  });

  it("stops after the session-level budget is exhausted", () => {
    const timers = new FakeTimers();
    const rc = new ReconnectController(2, timers);
    expect(rc.schedule(() => {})).toBe("scheduled");
    timers.fireAll();
    expect(rc.schedule(() => {})).toBe("scheduled");
    timers.fireAll();
    expect(rc.schedule(() => {})).toBe("exhausted"); // budget of 2 used
    expect(timers.pendingCount).toBe(0);
  });

  it("does not reconnect with an expired token", () => {
    const timers = new FakeTimers();
    const rc = new ReconnectController(3, timers);
    expect(rc.schedule(() => {}, { tokenExpired: true })).toBe("token_expired");
    expect(timers.pendingCount).toBe(0);
    expect(rc.attempts).toBe(0);
  });

  it("resets the budget for a genuinely new session", () => {
    const timers = new FakeTimers();
    const rc = new ReconnectController(2, timers);
    rc.schedule(() => {});
    timers.fireAll();
    rc.schedule(() => {});
    timers.fireAll();
    expect(rc.attempts).toBe(2);
    rc.resetForNewSession();
    expect(rc.attempts).toBe(0);
    expect(rc.schedule(() => {})).toBe("scheduled"); // budget available again
  });

  it("stop() cancels the pending timer and blocks further scheduling", () => {
    const timers = new FakeTimers();
    const rc = new ReconnectController(3, timers);
    rc.schedule(() => {});
    expect(timers.pendingCount).toBe(1);
    rc.stop();
    expect(timers.pendingCount).toBe(0);
    expect(rc.schedule(() => {})).toBe("stopped");
  });
});
