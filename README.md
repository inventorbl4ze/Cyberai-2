# CYBERAI 2.0

**CYRA — Knowledge • Conversation • Creativity**  
Created by **Oduyebo Abiola**.

CYBERAI 2.0 is a mobile-first web AI assistant with a shared Python API backend. The website can be installed on supported Android browsers as a Progressive Web App (PWA).

## Live services

- Website: https://inventorbl4ze.github.io/Cyberai-2/
- Python API: https://cyberai-2.onrender.com
- API health: https://cyberai-2.onrender.com/health
- API docs: https://cyberai-2.onrender.com/docs

## Current features

- Gemini-powered chat with short conversation context
- Retry and fallback model handling for temporary provider capacity errors
- Image and PDF attachments (up to 3 files, 8 MB each)
- TXT, Markdown and CSV text import
- Browser voice input where supported
- Speech playback for assistant replies
- Experimental real-time Gemini Live voice sessions (requires Live API model access and microphone permission)
- Recent chats stored locally in the browser
- Searchable local knowledge library with evergreen lessons, dated news and time-bounded weather forecasts
- PWA manifest, app icon and offline website shell
- Basic per-IP request throttling on the API

## Knowledge library and freshness

The website's **Learn something** and **Explore topics** sections open the searchable `knowledge-library.json` file. It keeps three kinds of information separate:

- `evergreen`: stable educational reference lessons with source links.
- `news`: dated reports, including a publication date and a data cut-off where applicable.
- `weather`: official forecasts with issue and validity times. These are not live observations; expired forecasts are labelled as expired in the library.

The knowledge library is a curated static snapshot. It does not make the chat backend a live news or weather service. Open the linked original source for the newest information.

## Install on Android

1. Open the website in Chrome.
2. Open the browser menu.
3. Choose **Install app** or **Add to Home screen** when offered.
4. Launch CYBERAI from the new home-screen icon.

The installed PWA is the first app delivery format. A separately packaged Play Store APK/AAB still requires an Android wrapper, signing, and release testing.

## Backend configuration

The backend is in `backend/` and uses FastAPI plus Google's official `google-genai` SDK.

Configure these private environment variables on the backend host:

- `GEMINI_API_KEY` — Google AI Studio API key
- `GEMINI_MODEL` — optional primary model (default: `gemini-3.8-flash`)
- `GEMINI_FALLBACK_MODEL` — optional fallback (default: `gemini-3.5-flash-lite`)
- `ALLOWED_ORIGINS` — comma-separated allowed browser origins
- `GEMINI_LIVE_MODEL` — optional Live API model (default: `gemini-3.8-live`)
- `MAX_LIVE_SESSIONS` — maximum concurrent Live Voice sessions per backend process (default: `3`)
- `OPENAI_API_KEY` — optional OpenAI API key for a text-only backup provider
- `OPENAI_MODEL` — optional backup model (default: `gpt-6-luna`)
- `ENABLE_OPENAI_FALLBACK` — set to `true` only after an adult account owner approves billing; defaults to `false`

**Never put either provider key in this repository, website JavaScript, or an Android package.** OpenAI fallback is disabled by default, requires a separately configured key, and only runs after a temporary Gemini capacity/service failure. It currently handles text-only requests; image/PDF attachments remain on Gemini.

## Important launch hardening

The built-in in-memory IP throttle is a basic safety net, not a complete production abuse-control system. Before a broad public launch, add shared rate limiting, user authentication, per-account quotas, monitoring, and a privacy/retention policy. Do not treat browser-local chat history as cloud backup.

## Development

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
uvicorn main:app --reload
```

API documentation is available at `/docs` while the backend is running.

