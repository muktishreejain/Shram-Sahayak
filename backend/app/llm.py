from __future__ import annotations

import json
import re
from typing import Any

from google import genai
from google.genai import types

from .config import ALLOWLIST, CRISIS_TYPES, GEMINI_API_KEY, GEMINI_MODELS, URGENCY_TYPES
from .prompts import build_user_prompt, system_prompt_for

UNKNOWN_FALLBACK = {
    "crisis_type": "other",
    "urgency": "medium",
    "summary_hi": "मैं केवल काम, वेतन, कार्यस्थल सुरक्षा और श्रमिक दस्तावेज़ों के सवालों में मदद करता हूँ। इस सवाल के लिए पक्की जानकारी नहीं मिली।",
    "steps_hi": [
        "e-Shram हेल्पलाइन 14434 पर कॉल करें।",
        "SAMADHAN पोर्टल पर शिकायत दर्ज करें: https://samadhan.labour.gov.in/",
        "नजदीकी CSC केंद्र पर जाकर मदद माँगें।",
    ],
    "document_issues": [],
    "sources": [
        {"name": "e-Shram", "url": "https://eshram.gov.in/"},
        {"name": "SAMADHAN", "url": "https://samadhan.labour.gov.in/"},
        {"name": "CSC locator", "url": "https://locator.csc.gov.in/"},
    ],
    "unknown": True,
}

UNKNOWN_FALLBACK_EN = {
    "crisis_type": "other",
    "urgency": "medium",
    "summary_hi": "I only help with work, wages, workplace safety, and worker documents. I could not confirm information for this question.",
    "steps_hi": [
        "Call the e-Shram helpline at 14434.",
        "Check the SAMADHAN portal for a complaint option: https://samadhan.labour.gov.in/",
        "Visit a nearby CSC centre for help.",
    ],
    "document_issues": [],
    "sources": [
        {"name": "e-Shram", "url": "https://eshram.gov.in/"},
        {"name": "SAMADHAN", "url": "https://samadhan.labour.gov.in/"},
        {"name": "CSC locator", "url": "https://locator.csc.gov.in/"},
    ],
    "unknown": True,
}


def _unknown_answer(language: str = "hi") -> dict[str, Any]:
    fallback = UNKNOWN_FALLBACK_EN if language == "en" else UNKNOWN_FALLBACK
    return {
        **fallback,
        "steps_hi": list(fallback["steps_hi"]),
        "sources": list(fallback["sources"]),
    }


def _document_issues(data: dict[str, Any], document_provided: bool) -> list[dict[str, str]]:
    if not document_provided:
        return []
    raw_issues = data.get("document_issues") or []
    if not isinstance(raw_issues, list):
        return []
    findings: list[dict[str, str]] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        issue = str(item.get("issue") or "").strip()
        action = str(item.get("action") or "").strip()
        if issue and action:
            findings.append({"issue": issue, "action": action})
        if len(findings) == 5:
            break
    return findings


def _unknown_with_document_issues(
    language: str,
    document_issues: list[dict[str, str]],
) -> dict[str, Any]:
    answer = _unknown_answer(language)
    answer["document_issues"] = document_issues
    return answer


def _client() -> genai.Client:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY नहीं मिला। aistudio.google.com/apikey से मुफ्त key लेकर .env में जोड़ें।"
        )
    return genai.Client(api_key=GEMINI_API_KEY)


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _allowed_urls(chunks: list[dict]) -> set[str]:
    urls = set(ALLOWLIST)
    urls.update(
        url
        for chunk in chunks
        if (url := str(chunk.get("source_url") or "").strip())
    )
    return urls


def validate_answer(
    data: dict[str, Any] | None,
    chunks: list[dict],
    language: str = "hi",
    document_provided: bool = False,
) -> dict[str, Any]:
    if not data or not isinstance(data, dict):
        return _unknown_answer(language)
    document_issues = _document_issues(data, document_provided)
    if not chunks or data.get("unknown") is True:
        return _unknown_with_document_issues(language, document_issues)

    crisis = str(data.get("crisis_type") or "other")
    if crisis not in CRISIS_TYPES:
        crisis = "other"
    urgency = str(data.get("urgency") or "medium")
    if urgency not in URGENCY_TYPES:
        urgency = "medium"
    if urgency == "critical" and crisis not in {"workplace_injury", "harassment"}:
        urgency = "high"

    raw_steps = data.get("steps_hi") or []
    if not isinstance(raw_steps, list):
        return _unknown_with_document_issues(language, document_issues)
    steps = [str(step).strip() for step in raw_steps if str(step).strip()][:5]
    if len(steps) < 3:
        return _unknown_with_document_issues(language, document_issues)

    english_text = [*steps, *(text for item in document_issues for text in item.values())]
    if language == "en" and any(re.search(r"[\u0900-\u097f]", value) for value in english_text):
        return _unknown_answer("en")

    allowed = _allowed_urls(chunks)
    source_names: dict[str, set[str]] = {}
    for chunk in chunks:
        url = str(chunk.get("source_url") or "").strip()
        title = str(chunk.get("title") or "").strip()
        if url and title:
            source_names.setdefault(url, set()).add(title)
    for name, url in {
        "SAMADHAN": "https://samadhan.labour.gov.in/",
        "e-Shram": "https://eshram.gov.in/",
        "myScheme": "https://www.myscheme.gov.in/",
        "Shram Suvidha": "https://shramsuvidha.gov.in/",
        "National Career Service": "https://ncs.gov.in/",
        "CSC locator": "https://locator.csc.gov.in/",
    }.items():
        source_names.setdefault(url, set()).add(name)

    sources_out: list[dict[str, str]] = []
    raw_sources = data.get("sources") or []
    if not isinstance(raw_sources, list):
        raw_sources = []
    for item in raw_sources:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        name = str(item.get("name") or "").strip()
        if url in allowed and name in source_names.get(url, set()):
            candidate = {"name": name, "url": url}
            if candidate not in sources_out:
                sources_out.append(candidate)
    if not sources_out:
        return _unknown_with_document_issues(language, document_issues)

    summary = str(data.get("summary_hi") or "").strip()
    if not summary:
        return _unknown_with_document_issues(language, document_issues)
    if language == "en" and re.search(r"[\u0900-\u097f]", summary):
        return _unknown_answer("en")

    return {
        "crisis_type": crisis,
        "urgency": urgency,
        "summary_hi": summary,
        "steps_hi": steps,
        "document_issues": document_issues,
        "sources": sources_out,
        "unknown": False,
    }


def generate_guidance(
    transcript: str,
    doc_text: str,
    chunks: list[dict],
    images: list[tuple[bytes, str]] | None = None,
    language: str = "hi",
    document_provided: bool = False,
) -> dict[str, Any]:
    language = "en" if language == "en" else "hi"
    user_text = build_user_prompt(transcript, doc_text, chunks, language)
    image_parts = [
        types.Part.from_bytes(data=blob, mime_type=mime) for blob, mime in (images or [])
    ]

    client = _client()
    last_error = ""
    for model in GEMINI_MODELS:
        try:
            def call(extra: str = "") -> str:
                contents: list[Any] = [user_text + extra, *image_parts]
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        response_mime_type="application/json",
                        system_instruction=system_prompt_for(language),
                    ),
                )
                return response.text or ""

            parsed = _parse_json(call())
            if parsed is None:
                parsed = _parse_json(call("\n\nReturn JSON only. No markdown."))
            return validate_answer(parsed, chunks, language, document_provided)
        except Exception as exc:
            last_error = str(exc)
            if "404" in last_error or "NOT_FOUND" in last_error:
                continue
            if "API_KEY" in last_error.upper() or "UNAUTHENTICATED" in last_error.upper():
                detail = (
                    "The Gemini API key is invalid. Check your free key."
                    if language == "en"
                    else "GEMINI_API_KEY सही नहीं है। अपनी मुफ्त key जाँचें।"
                )
                raise RuntimeError(detail) from exc
            detail = (
                "Gemini could not prepare an answer. Check your internet connection and API key."
                if language == "en"
                else "Gemini से जवाब नहीं मिला। इंटरनेट और API key जाँचें।"
            )
            raise RuntimeError(detail) from exc
    if last_error:
        detail = (
            "A Gemini Flash model is unavailable. Check model availability."
            if language == "en"
            else "Gemini का Flash मॉडल उपलब्ध नहीं है। मॉडल की उपलब्धता जाँचें।"
        )
        raise RuntimeError(detail)
    return _unknown_answer(language)
