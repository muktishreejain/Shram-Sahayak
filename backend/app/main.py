from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader

from .config import (
    GEMINI_API_KEY,
    MAX_DOCUMENT_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    UPLOADS_DIR,
    ensure_dirs,
)
from .db import get_case, init_db, insert_case, list_cases
from .llm import generate_guidance
from .rag import query_chunks
from .stt import transcribe_audio

IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

app = FastAPI(title="Shram Sahayak")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "app": "shram-sahayak"}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = "en") -> dict:
    language = "en" if language == "en" else "hi"
    content = await _read_upload(audio, MAX_UPLOAD_BYTES, language)
    try:
        text = transcribe_audio(audio.filename or "audio.webm", content, audio.content_type)
    except ValueError as exc:
        detail = str(exc) if language == "hi" else "The audio is empty or invalid. Please try another recording."
        raise HTTPException(status_code=400, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=400,
            detail=_transcription_error_message(exc, language),
        ) from exc
    return {"transcript": text}


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _transcription_error_message(error: RuntimeError, language: str) -> str:
    message = str(error).lower()
    if "invalid_api_key" in message or "invalid api key" in message or "unauthorized" in message:
        return (
            "Groq rejected the API key. Create a new free key at console.groq.com and replace GROQ_API_KEY in the project .env file."
            if language == "en"
            else "Groq ने API key स्वीकार नहीं की। console.groq.com पर नई मुफ्त key बनाएँ और project की .env फ़ाइल में GROQ_API_KEY बदलें।"
        )
    if "groq_api_key" in message:
        return (
            "GROQ_API_KEY is missing. Add a free key from console.groq.com to the project .env file."
            if language == "en"
            else "GROQ_API_KEY नहीं मिली। console.groq.com से मुफ्त key लेकर project की .env फ़ाइल में जोड़ें।"
        )
    return (
        "Speech recognition failed. Check your Groq API key and try again."
        if language == "en"
        else "आवाज़ समझ नहीं आई। Groq API key जाँचें और फिर कोशिश करें।"
    )


async def _read_upload(upload: UploadFile, limit: int, language: str = "hi") -> bytes:
    content = bytearray()
    while True:
        chunk = await upload.read(min(1024 * 1024, limit + 1 - len(content)))
        if not chunk:
            return bytes(content)
        content.extend(chunk)
        if len(content) > limit:
            detail = (
                "The file must be smaller than 20 MB."
                if language == "en"
                else "फ़ाइल 20 MB से छोटी होनी चाहिए।"
            )
            raise HTTPException(status_code=413, detail=detail)


def _file_kind(upload: UploadFile, language: str = "hi") -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    mime = (upload.content_type or "").lower()
    if suffix not in ALLOWED_EXTENSIONS:
        detail = "Only JPG, PNG, or PDF files are supported." if language == "en" else "केवल JPG, PNG या PDF भेजें।"
        raise HTTPException(status_code=400, detail=detail)
    if suffix == ".pdf":
        if mime not in {"", "application/pdf", "application/octet-stream"}:
            detail = "The file type does not match its name." if language == "en" else "फ़ाइल का प्रकार और नाम मेल नहीं खाते।"
            raise HTTPException(status_code=400, detail=detail)
        return "pdf"
    expected = {"image/png"} if suffix == ".png" else {"image/jpeg", "image/jpg"}
    if mime not in {"", "application/octet-stream", *expected}:
        detail = "The file type does not match its name." if language == "en" else "फ़ाइल का प्रकार और नाम मेल नहीं खाते।"
        raise HTTPException(status_code=400, detail=detail)
    return "image"


@app.post("/api/ask")
async def ask(
    text: str | None = Form(None),
    audio: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(default=None),
    language: str = Form("en"),
) -> dict:
    language = "en" if language == "en" else "hi"
    has_audio = audio is not None and bool(audio.filename)
    has_files = any(upload.filename for upload in files or [])
    if not has_audio and not (text and text.strip()) and not has_files:
        raise HTTPException(
            status_code=400,
            detail=(
                "Speech or a written message is required."
                if language == "en"
                else "आवाज़ या लिखा हुआ संदेश ज़रूरी है।"
            ),
        )

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail=(
                "GEMINI_API_KEY is missing. Get a free key at aistudio.google.com/apikey and add it to .env."
                if language == "en"
                else "GEMINI_API_KEY नहीं मिला। aistudio.google.com/apikey से मुफ्त key लेकर .env में जोड़ें।"
            ),
        )

    parts: list[str] = []
    saved_names: list[str] = []
    doc_text_bits: list[str] = []
    images: list[tuple[bytes, str]] = []

    if has_audio and audio is not None:
        audio_bytes = await _read_upload(audio, MAX_UPLOAD_BYTES, language)
        if audio_bytes:
            try:
                spoken = transcribe_audio(
                    audio.filename or "audio.webm",
                    audio_bytes,
                    audio.content_type,
                )
            except ValueError as exc:
                detail = str(exc) if language == "hi" else "Audio must be a valid recording smaller than 20 MB."
                raise HTTPException(status_code=400, detail=detail) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=_transcription_error_message(exc, language),
                ) from exc
            parts.append(spoken)

    if text and text.strip():
        parts.append(text.strip())

    for upload in files or []:
        if not upload.filename:
            continue
        kind = _file_kind(upload, language)
        content = await _read_upload(upload, MAX_UPLOAD_BYTES, language)
        if not content:
            continue
        suffix = Path(upload.filename).suffix.lower()
        mime = (upload.content_type or "").lower()
        if kind == "pdf":
            try:
                extracted = _pdf_text(content)
            except Exception as exc:
                detail = "Could not read this PDF. Try another file." if language == "en" else "PDF पढ़ा नहीं जा सका। दूसरी फ़ाइल भेजें।"
                raise HTTPException(status_code=400, detail=detail) from exc
            if extracted:
                doc_text_bits.append(extracted)
        else:
            safe_mime = mime if mime in IMAGE_TYPES else (
                "image/png" if suffix == ".png" else "image/jpeg"
            )
            if safe_mime == "image/jpg":
                safe_mime = "image/jpeg"
            images.append((content, safe_mime))

        stored = f"{uuid4().hex}{suffix}"
        (UPLOADS_DIR / stored).write_bytes(content)
        saved_names.append(upload.filename)

    if not parts and saved_names:
        parts.append(
            "Review the uploaded document for missing, unreadable, or inconsistent details."
            if language == "en"
            else "दिए गए दस्तावेज़ में छूटी, अस्पष्ट या अलग जानकारी जाँचें।"
        )
    if not parts:
        raise HTTPException(
            status_code=400,
            detail=(
                "Speech, a written message, or a document is required."
                if language == "en"
                else "आवाज़, लिखा हुआ संदेश या दस्तावेज़ देना ज़रूरी है।"
            ),
        )

    transcript = "\n".join(parts)
    doc_text = "\n\n".join(doc_text_bits)[:MAX_DOCUMENT_TEXT_CHARS]
    query = f"{transcript}\n{doc_text}".strip()
    try:
        chunks = query_chunks(query, k=5)
    except ModuleNotFoundError as exc:
        if exc.name not in {"chromadb", "sentence_transformers"}:
            raise
        detail = (
            "The knowledge base is not installed. Install backend requirements and run `python -m app.ingest` from the backend folder."
            if language == "en"
            else "ज्ञान आधार तैयार नहीं है। backend में requirements इंस्टॉल करके `python -m app.ingest` चलाएँ।"
        )
        raise HTTPException(status_code=503, detail=detail) from exc

    try:
        answer = generate_guidance(
            transcript,
            doc_text,
            chunks,
            images=images,
            language=language,
            document_provided=bool(saved_names),
        )
    except RuntimeError as exc:
        detail = str(exc)
        if language == "en" and detail.startswith("GEMINI_API_KEY"):
            detail = "The Gemini API key is invalid. Check the free key in your .env file."
        elif language == "en":
            detail = "Gemini could not prepare an answer. Check your API key and try again."
        raise HTTPException(status_code=400, detail=detail) from exc

    document_issues = answer.get("document_issues", [])
    case_id = insert_case(
        transcript=transcript,
        crisis_type=answer["crisis_type"],
        urgency=answer["urgency"],
        summary_hi=answer["summary_hi"],
        steps_hi=answer["steps_hi"],
        sources=answer["sources"],
        unknown=answer["unknown"],
        filenames=saved_names,
        language=language,
        document_issues=document_issues,
    )
    return {
        "id": case_id,
        "transcript": transcript,
        "language": language,
        "document_issues": document_issues,
        **answer,
        "filenames": saved_names,
    }


@app.get("/api/cases")
def cases() -> dict:
    return {"cases": list_cases(20)}


@app.get("/api/cases/{case_id}")
def case_detail(case_id: int, language: str = "en") -> dict:
    row = get_case(case_id)
    if row is None:
        detail = "Case not found." if language == "en" else "केस नहीं मिला।"
        raise HTTPException(status_code=404, detail=detail)
    return row
