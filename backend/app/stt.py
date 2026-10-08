from __future__ import annotations

import httpx

from .config import GROQ_API_KEY, MAX_AUDIO_BYTES

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MODELS = ["whisper-large-v3-turbo", "whisper-large-v3"]


def transcribe_audio(filename: str, content: bytes, content_type: str | None) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY नहीं मिला। console.groq.com से मुफ्त key लेकर .env में जोड़ें।"
        )
    if len(content) > MAX_AUDIO_BYTES:
            raise ValueError("ऑडियो फ़ाइल 20 MB से छोटी होनी चाहिए।")
    if not content:
            raise ValueError("ऑडियो फ़ाइल खाली है।")

    mime = content_type or "application/octet-stream"
    last_error = ""
    for model in MODELS:
        try:
            with httpx.Client(timeout=90.0) as client:
                response = client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    files={"file": (filename, content, mime)},
                    data={"model": model},
                )
        except httpx.RequestError as exc:
            raise RuntimeError("Whisper से संपर्क नहीं हो पाया। इंटरनेट कनेक्शन जाँचें।") from exc
        if response.status_code == 200:
            text = (response.json().get("text") or "").strip()
            if not text:
                raise RuntimeError("आवाज़ समझ नहीं आई। कृपया फिर से बोलें।")
            return text
        last_error = response.text
        if response.status_code not in (400, 404):
            break
    raise RuntimeError(f"Whisper सेवा ने ऑडियो स्वीकार नहीं किया: {last_error[:250]}")
