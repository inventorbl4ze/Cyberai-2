"""CYBERAI 2.0 backend — Gemini API gateway.

The Gemini API key is read only from the server environment. Never place it
in frontend code, source control, or a client application.
"""
import logging
import os
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


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=12)


class ChatResponse(BaseModel):
    answer: str
    model: str


SYSTEM_INSTRUCTION = """
You are CYRA, the helpful AI assistant inside CYBERAI 2.0, created by Oduyebo
Abiola. Be clear, warm, accurate, and honest about uncertainty. Explain
educational topics step by step. Do not claim to see, hear, browse, or remember
anything unless the relevant information is actually provided to you.
"""


def generate_answer(payload: ChatRequest) -> str:
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

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=payload.message)],
        )
    )

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
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
        return answer
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
        answer = await run_in_threadpool(generate_answer, payload)
        return ChatResponse(answer=answer, model=MODEL_NAME)
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
