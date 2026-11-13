# CYBERAI 2.0 — Python AI Engine

This FastAPI service is the shared backend for the CYBERAI 2.0 website and Android app. It connects to Google AI Studio through the official `google-genai` Python SDK.

## 1. Configure the API key

Create a private environment variable named `GEMINI_API_KEY` on the server or hosting provider. For local development, copy `.env.example` to `.env` and put your key in that local file.

**Never paste the real key into GitHub, frontend JavaScript, an Android app, screenshots, or a public chat.** The `.env` file is ignored by Git.

## 2. Install and run locally

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment, then run:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

The API runs at `http://127.0.0.1:8000`. Interactive API docs are at `/docs`.

## 3. Endpoints

- `GET /` — service information
- `GET /health` — service and configuration status (never returns the key)
- `POST /api/chat` — sends a message and optional recent conversation history to Gemini

Example request:

```json
{
  "message": "Hello CYRA",
  "history": []
}
```

## 4. Before public launch

Deploy the backend to a Python-capable host, set `GEMINI_API_KEY` as a private server secret, set `ALLOWED_ORIGINS` to the exact production web origin, and add authentication, per-user quotas, and abuse protection before opening the API to public traffic. The Android app must call this backend; it must never contain the Gemini key.

Created by Oduyebo Abiola.
