# Live Interview — Manual QA

Manual test plan for the experimental **Live Interview** mode (Gemini Live).
These require a real browser, microphone and a configured Gemini key, so they are
**not** part of the automated suite (CI never calls Gemini). Run them before
relying on live mode.

## Preconditions

- `pip install -e ".[live]"` and build the component:
  `cd components/live_interviewer/frontend && npm install && npm run build`.
- Set `GEMINI_API_KEY` (secrets or env). Confirm the app shows the **Live** option
  and does not display the fallback.
- Start an interview so a canonical question is on screen, then pick **Live**.

## Environment matrix

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| 1 | Chrome — happy path | Grant mic, let interviewer speak, answer aloud | Interviewer speaks the canonical question; your transcript appears; review + submit reaches evaluation |
| 2 | Safari — happy path | Same as #1 in Safari | Works (or a clear message if the browser is unsupported); audio does not glitch |
| 3 | Microphone granted | First use → allow the mic prompt | Capture starts; status shows speaking/listening |
| 4 | Microphone denied | Deny the mic prompt | Clear error; no crash; can switch to Record/Text without losing progress |
| 5 | Microphone removed mid-session | Unplug/disable mic mid-answer | Clear error/status; bounded reconnect or graceful stop; earlier answers preserved |
| 6 | Network disconnected | Kill Wi-Fi mid-session | Status shows reconnecting; stops after the bounded max; fallback offered; no infinite loop |
| 7 | Candidate interruption (barge-in) | Start talking while interviewer is speaking | Interviewer stops immediately; queued interviewer audio is discarded; no overlap |
| 8 | Interviewer interruption | Interviewer output interrupted by server | Playback stops cleanly; state stays consistent |
| 9 | Long answer | Speak for several minutes | No runaway memory; transcript accumulates; turn completes normally |
| 10 | Silence | Say nothing after the question | No spurious submit; candidate can retry or switch modes |
| 11 | Reconnect | Trigger a transient drop | Reconnects up to the bounded limit with backoff; resumes or falls back |
| 12 | Deep Dive | After evaluation choose **Explore this further** | Deep Dive question (from the branching service) is spoken, answered aloud, evaluated, bounded by max depth, returnable to the main interview |
| 13 | Session completion | Finish the planned questions in live mode | Interview completes; report available; no dangling audio/WebSocket |

## Security checks (every run)

- Open DevTools → Network/Console: confirm the **permanent** Gemini key never
  appears; only the ephemeral token is used. Tokens are not logged.
- Confirm no raw audio is written to disk or persisted between sessions.
- Confirm the transcript shown for review is verbatim (not "improved").

## Fallback checks

- With `GEMINI_API_KEY` unset (or the component not built), selecting **Live**
  shows *"Live interview is temporarily unavailable."* with **Continue with
  recorded voice** and **Continue with text**, and no completed answers are lost.

## Cost

- Gemini usage is shown separately from OpenRouter LLM cost; no dollar figure is
  claimed unless a real rate is configured.
