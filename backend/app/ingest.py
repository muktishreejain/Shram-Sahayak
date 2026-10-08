from __future__ import annotations

import re
from pathlib import Path

from .config import KNOWLEDGE_DIR
from .rag import get_collection


def _parse_header(text: str) -> tuple[str, str, str, str]:
    title = ""
    source_url = ""
    topic = ""
    body_lines = []
    for line in text.splitlines():
        low = line.strip()
        if low.lower().startswith("title:"):
            title = low.split(":", 1)[1].strip()
        elif low.lower().startswith("source_url:"):
            source_url = low.split(":", 1)[1].strip()
        elif low.lower().startswith("topic:"):
            topic = low.split(":", 1)[1].strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return title, source_url, topic, body


def _paragraphs(body: str) -> list[str]:
    parts = re.split(r"\n\s*\n", body)
    chunks = [p.strip() for p in parts if p.strip()]
    return chunks or [body]


def ingest() -> int:
    files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not files:
        raise SystemExit(f"No markdown files in {KNOWLEDGE_DIR}")

    collection = get_collection()
    existing = collection.get()
    if existing.get("ids"):
        collection.delete(ids=existing["ids"])

    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    n = 0
    for path in files:
        raw = path.read_text(encoding="utf-8")
        title, source_url, topic, body = _parse_header(raw)
        if not title:
            title = path.stem
        if not topic:
            topic = path.stem
        for i, para in enumerate(_paragraphs(body)):
            n += 1
            ids.append(f"{path.stem}-{i}")
            docs.append(para)
            metas.append(
                {
                    "title": title,
                    "source_url": source_url,
                    "topic": topic,
                    "file": path.name,
                }
            )
    collection.add(ids=ids, documents=docs, metadatas=metas)
    return n


if __name__ == "__main__":
    count = ingest()
    print(f"Ingested {count} chunks into collection worker_help")
