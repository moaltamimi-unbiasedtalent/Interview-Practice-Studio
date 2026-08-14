# Live Interviewer — Streamlit component (frontend)

Real-time Gemini Live interface for the experimental Live Interview mode. The
frontend owns all high-frequency audio/WebSocket work; the Python backend stays
the authoritative interview intelligence (OpenRouter) and only supplies the
canonical question and a short-lived **ephemeral token**.

## Responsibilities

- Microphone permission + capture (`getUserMedia`)
- Resample to 16 kHz mono and emit ~30 ms PCM16 chunks (`pcm-worklet.js`)
- Gemini Live WebSocket via the ephemeral token only (`gemini.ts`)
- Playback of interviewer audio (24 kHz)
- Live candidate + interviewer transcripts
- Connection status, mute/unmute, stop, **bounded** reconnect
- Interruption / barge-in: stop interviewer audio, discard stale audio
- Turn state machine mirrored from the backend (`state.ts`)

## Security

The component receives only the **ephemeral token** (never the permanent Gemini
key). Tokens are never logged or stored in local storage.

## Build

```bash
npm install
npm run build      # emits dist/ ; the Python wrapper serves dist/ when present
npm test           # vitest unit tests (state machine)
```

Until `dist/` exists, `components.live_interviewer.is_available()` returns
`False` and the app falls back to Voice or Text practice. CI never builds this or
calls Gemini.
