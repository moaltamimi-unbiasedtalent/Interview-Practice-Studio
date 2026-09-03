# Privacy Review

A consolidated statement of what the product does and does not do with personal
data, with the guarantees backed by automated tests.

## Camera / video

- **The product never requests camera access.** The visual-engagement coach was
  withdrawn: there is no camera capture, no frame processing, and no MediaPipe in
  the running product. An end-to-end test asserts that normal Interview Practice
  never calls `getUserMedia` for video.
- No screenshots, face landmarks, biometric templates or visual metrics are
  produced or persisted.

## Audio (Voice / Live)

- **Raw audio storage defaults to off.** Recorded audio is used only for the
  active transcription request and is not written to disk or kept in session.
- Only the transcript (text) and numeric delivery metrics are retained; audio
  bytes are never logged.

## Transcripts & interview content

- Persisted **only when the candidate has an account/session** and only per the
  repository (user-scoped). Candidates can **export** all their data and
  **delete** individual interviews or everything (Settings). Deletion issues a
  real `DELETE` (cascade) — verified by tests.
- Only **appropriate** data is stored: identity, configuration, questions,
  answers/evaluations, timing metrics, report and usage/cost. Never: camera
  video, face frames, biometric templates, visual metrics, permanent API keys, or
  raw audio.

## Logging

- Generation-failure logs contain **safe metadata only** (task, schema, model,
  request id, finish reason, token counts) — never request/response content,
  candidate answers, audio bytes, transcripts, keys or tokens (asserted by
  tests).

## Identity & access

- Auth via Streamlit OIDC; `st.user` is read in exactly one place (`src/auth.py`).
- **Cross-user isolation:** every repository method is user-scoped; one user can
  never read, export or delete another's data (asserted by tests).

## Secrets

- The permanent Gemini key is backend-only; the browser receives only a
  short-lived ephemeral token (never logged). Google Speech uses ADC. No secret
  is committed or placed in the Docker image.

## Retention

Interview data is kept until the candidate deletes it; there is no background
retention beyond that. See `constants.DATA_RETENTION_NOTE`.
