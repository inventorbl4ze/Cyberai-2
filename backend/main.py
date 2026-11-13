"""CYBERAI 2.0 backend — Gemini API gateway.

The Gemini API key is read only from the server environment. Never place it
in frontend code, source control, or a client application.
"""
import asyncio
import base64
import binascii
import logging
import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Literal

logger = logging.getLogger("cyberai")

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel, Field

APP_NAME = "CYBERAI 2.0"
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
OPENAI_FALLBACK_ENABLED = os.getenv("ENABLE_OPENAI_FALLBACK", "false").lower() == "true"

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


RATE_LIMIT = 15
RATE_WINDOW_SECONDS = 60
_request_times: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()


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


def generate_openai_answer(payload: ChatRequest) -> tuple[str, str]:
    """Optional text-only backup. Disabled unless explicitly enabled on the host."""
    if not OPENAI_FALLBACK_ENABLED or not OPENAI_API_KEY:
        raise RuntimeError("OpenAI fallback is not enabled or configured.")
    if payload.attachments:
        raise RuntimeError("OpenAI fallback currently supports text-only requests.")
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        conversation = [
            {"role": item.role, "content": item.content}
            for item in payload.history[-12:]
        ]
        conversation.append({"role": "user", "content": payload.message})
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_INSTRUCTION,
            input=conversation,
            max_output_tokens=2048,
        )
        answer = (response.output_text or "").strip()
        if not answer:
            raise RuntimeError("OpenAI returned an empty response.")
        return answer, f"openai:{OPENAI_MODEL}"
    finally:
        client.close()


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
        "openai_fallback_configured": bool(OPENAI_API_KEY),
        "openai_fallback_enabled": bool(OPENAI_FALLBACK_ENABLED and OPENAI_API_KEY),
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request):
    # Basic per-process abuse protection. Use a shared rate-limit store at scale.
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _rate_lock:
        recent = _request_times[client_ip]
        while recent and now - recent[0] > RATE_WINDOW_SECONDS:
            recent.popleft()
        if len(recent) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Too many messages in a short time. Please wait a minute and try again.")
        recent.append(now)

    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="The AI service is not configured yet. Add GEMINI_API_KEY to the backend environment.",
        )

    try:
        answer, used_model = await run_in_threadpool(generate_answer, payload)
        return ChatResponse(answer=answer, model=used_model)
    except HTTPException:
        raise
    except TemporaryGeminiUnavailable:
        logger.error("Gemini remained temporarily unavailable after retries (model=%s)", MODEL_NAME)
        if OPENAI_FALLBACK_ENABLED and OPENAI_API_KEY and not payload.attachments:
            try:
                answer, used_model = await run_in_threadpool(generate_openai_answer, payload)
                return ChatResponse(answer=answer, model=used_model)
            except Exception as fallback_exc:
                logger.exception(
                    "Optional OpenAI fallback failed (model=%s, exception_type=%s)",
                    OPENAI_MODEL,
                    type(fallback_exc).__name__,
                )
        raise HTTPException(
            status_code=503,
            detail="The primary AI service is temporarily busy. Please try again shortly.",
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


@app.websocket("/api/live")
async def live_voice(websocket: WebSocket):
    """Optional real-time voice session. The Gemini key remains server-side."""
    if not API_KEY:
        await websocket.close(code=1011, reason="AI service is not configured.")
        return

    await websocket.accept()
    client = genai.Client(api_key=API_KEY)
    live_model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": "Kore"}
            }
        },
        "system_instruction": SYSTEM_INSTRUCTION,
    }

    try:
        async with client.aio.live.connect(model=live_model, config=config) as session:
            async def send_browser_input():
                while True:
                    packet = await websocket.receive_json()
                    if packet.get("type") == "stop":
                        return
                    if packet.get("text"):
                        await session.send_realtime_input(text=str(packet["text"])[:2000])
                    audio = packet.get("audio")
                    if audio:
                        try:
                            raw = base64.b64decode(audio, validate=True)
                        except (binascii.Error, ValueError):
                            await websocket.send_json({"type": "error", "message": "Invalid audio packet."})
                            continue
                        if raw and len(raw) <= 128_000:
                            await session.send_realtime_input(
                                audio=types.Blob(data=raw, mime_type="audio/pcm;rate=16000")
                            )

            async def receive_model_output():
                async for message in session.receive():
                    content = getattr(message, "server_content", None)
                    if not content:
                        continue
                    transcription = getattr(content, "input_transcription", None)
                    if transcription and getattr(transcription, "text", None):
                        await websocket.send_json({"type": "transcript", "text": transcription.text})
                    turn = getattr(content, "model_turn", None)
                    if turn:
                        for part in (getattr(turn, "parts", None) or []):
                            inline = getattr(part, "inline_data", None)
                            if inline and getattr(inline, "data", None):
                                encoded = base64.b64encode(inline.data).decode("ascii")
                                await websocket.send_json({"type": "audio", "data": encoded})
                            elif getattr(part, "text", None):
                                await websocket.send_json({"type": "text", "text": part.text})
                    if getattr(content, "turn_complete", False):
                        await websocket.send_json({"type": "turn_complete"})

            input_task = asyncio.create_task(send_browser_input())
            output_task = asyncio.create_task(receive_model_output())
            done, pending = await asyncio.wait(
                {input_task, output_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                exception = task.exception()
                if exception:
                    raise exception
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Gemini Live voice session failed")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "Live voice could not start. Check the Live API model access and try again."
            })
        except Exception:
            pass
    finally:
        client.close()
