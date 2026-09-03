// Pure, DOM/WebSocket-free Live-session lifecycle helpers, unit-tested in
// isolation: session identity (what materially requires a restart), ephemeral
// token-expiry enforcement, and a bounded, idempotent reconnect controller.
// Interview intelligence stays in Python; this only governs the realtime shell.

export interface LiveConfig {
  model: string;
  ephemeral_token: string;
  token_expires_at: number; // epoch SECONDS (0/absent = unknown → treated valid)
  input_sample_rate: number;
  output_sample_rate: number;
  chunk_ms: number;
  max_reconnects: number;
  question?: string;
  session_id?: string;
  system_instruction?: string;
}

// A stable identity of the fields that materially require a new Live session.
// Never includes the secret token value — token *rotation* is captured by
// token_expires_at (which changes when Python mints a fresh token).
export function sessionIdentity(cfg: LiveConfig): string {
  return JSON.stringify([
    cfg.session_id ?? null,
    cfg.question ?? null,
    cfg.model,
    cfg.token_expires_at ?? null,
    cfg.system_instruction ?? null,
  ]);
}

// A token with a known expiry that is at/after `nowMs` (minus a small skew) is
// expired. An absent/zero expiry is treated as "unknown, do not block".
export function isTokenExpired(cfg: LiveConfig, nowMs: number, skewMs = 1000): boolean {
  if (!cfg.token_expires_at) return false;
  return nowMs >= cfg.token_expires_at * 1000 - skewMs;
}

export type ScheduleOutcome =
  | "scheduled"
  | "already_pending"
  | "stopped"
  | "token_expired"
  | "exhausted";

export interface TimerHost {
  set(fn: () => void, ms: number): number;
  clear(id: number): void;
}

const realTimers: TimerHost = {
  set: (fn, ms) => window.setTimeout(fn, ms),
  clear: (id) => window.clearTimeout(id),
};

// Bounded reconnect: at most ONE pending timer and ONE session-level attempt
// budget. A successful reconnect clears the pending timer but does NOT reset the
// budget (so repeated drop/reconnect cycles remain bounded); only a NEW session
// resets it. schedule() is idempotent — safe to call from both onerror and
// onclose.
export class ReconnectController {
  attempts = 0;
  private timer: number | null = null;
  private stopped = false;

  constructor(
    private maxAttempts: number,
    private timers: TimerHost = realTimers,
  ) {}

  get pending(): boolean {
    return this.timer !== null;
  }

  schedule(cb: () => void, opts: { tokenExpired?: boolean } = {}): ScheduleOutcome {
    if (this.stopped) return "stopped";
    if (this.timer !== null) return "already_pending"; // one timer maximum
    if (opts.tokenExpired) return "token_expired";
    if (this.attempts >= this.maxAttempts) return "exhausted";
    this.attempts += 1;
    const delay = Math.min(1000 * 2 ** (this.attempts - 1), 8000);
    this.timer = this.timers.set(() => {
      this.timer = null;
      cb();
    }, delay);
    return "scheduled";
  }

  // A connection succeeded: cancel any pending retry but KEEP the attempt count.
  onConnected(): void {
    this.cancel();
  }

  cancel(): void {
    if (this.timer !== null) {
      this.timers.clear(this.timer);
      this.timer = null;
    }
  }

  // A genuinely new session/config: cancel timer and reset the budget.
  resetForNewSession(): void {
    this.cancel();
    this.attempts = 0;
    this.stopped = false;
  }

  stop(): void {
    this.stopped = true;
    this.cancel();
  }
}
