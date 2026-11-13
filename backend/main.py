"""CYBERAI 2.0 backend — Gemini API gateway.

The Gemini API key is read only from the server environment. Never place it
in frontend code, source control, or a client application.
"""
import base64
import binascii
import logging
import os
import time
from typing import Literal

logger = logging.getLogger("cyberai")

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

APP_NAME = "CYBERAI 2.0"
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
API_KEY = os.getenv("GEMINI_API_KEY")

app = FastAPI(
    title=APP_NAME,
    description="Shared AI engine for CYBERAI 2.0 web and Android clients.",
    version="0.1.0",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "https://inventorbl4ze.github.io,http://localhost:5173,http://localhost:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatAttachment(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "application/pdf"]
    data_base64: str = Field(min_length=1, max_length=11_200_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=12)
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=3)


class ChatResponse(BaseModel):
    answer: str
    model: str


SYSTEM_INSTRUCTION = """
You are CYRA, the helpful AI assistant inside CYBERAI 2.0, created by Oduyebo
Abiola. Be clear, warm, accurate, and honest about uncertainty. Explain
educational topics step by step. Do not claim to see, hear, browse, or remember
anything unless the relevant information is actually provided to you.
"""


class TemporaryGeminiUnavailable(Exception):
    """Raised when Gemini remains temporarily unavailable after retries."""


def _http_status(exc: Exception) -> int | None:
    """Read the HTTP status across google-genai exception versions."""
    for value in (
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    ):
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    return None


def generate_answer(payload: ChatRequest) -> tuple[str, str]:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured on the server.")

    client = genai.Client(api_key=API_KEY)
    contents: list[types.Content] = []

    # Keep only a short, validated conversation window.
    for item in payload.history[-12:]:
        role = "model" if item.role == "assistant" else "user"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=item.content)],
            )
        )

    user_parts = [types.Part.from_text(text=payload.message)]
    for attachment in payload.attachments:
        try:
            raw = base64.b64decode(attachment.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="One of the attachments is not valid base64 data.") from exc
        if not raw or len(raw) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Each attachment must be smaller than 8 MB.")
        user_parts.append(types.Part.from_text(text=f"Attached file: {attachment.name}"))
        user_parts.append(types.Part.from_bytes(data=raw, mime_type=attachment.mime_type))

    contents.append(types.Content(role="user", parts=user_parts))

    try:
        # Try the primary model first, then a lighter model if Google is overloaded.
        models = [MODEL_NAME]
        if FALLBACK_MODEL and FALLBACK_MODEL != MODEL_NAME:
            models.append(FALLBACK_MODEL)

        for model_index, model_name in enumerate(models):
            delays = (1, 2, 4) if model_index == 0 else (1,)
            for attempt, delay in enumerate(delays, start=1):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            temperature=0.7,
                            max_output_tokens=2048,
                        ),
                    )
                    answer = (response.text or "").strip()
                    if not answer:
                        raise RuntimeError("The model returned an empty response.")
                    return answer, model_name
                except Exception as exc:
                    status_code = _http_status(exc)
                    if status_code not in (429, 500, 502, 503, 504):
                        raise
                    if attempt < len(delays):
                        logger.warning(
                            "Gemini model %s temporarily unavailable (status=%s); retry %s/%s in %s seconds",
                            model_name, status_code, attempt, len(delays), delay,
                        )
                        time.sleep(delay)
                        continue
                    if model_index < len(models) - 1:
                        logger.warning(
                            "Gemini model %s remained unavailable (status=%s); switching to fallback %s",
                            model_name, status_code, models[model_index + 1],
                        )
                        break
                    raise TemporaryGeminiUnavailable() from exc
        raise TemporaryGeminiUnavailable()
    finally:
        client.close()


@app.get("/")
async def root():
    return {
        "service": APP_NAME,
        "status": "online",
        "message": "CYBERAI 2.0 API is ready.",
    }


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": APP_NAME,
        "model": MODEL_NAME,
        "fallback_model": FALLBACK_MODEL,
        "api_key_configured": bool(API_KEY),
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="The AI service is not configured yet. Add GEMINI_API_KEY to the backend environment.",
        )

    try:
        answer, used_model = await run_in_threadpool(generate_answer, payload)
        return ChatResponse(answer=answer, model=used_model)
    except TemporaryGeminiUnavailable:
        logger.error("Gemini remained temporarily unavailable after retries (model=%s)", MODEL_NAME)
        raise HTTPException(
            status_code=503,
            detail="Google's AI service is temporarily busy. Please try again shortly.",
        )
    except Exception as exc:
        # Keep provider details in server logs only; never expose them to clients.
        logger.exception(
            "Gemini request failed (model=%s, exception_type=%s)",
            MODEL_NAME,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="CYRA could not complete that message. Please try again.",
        )
