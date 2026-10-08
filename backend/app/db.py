from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import SQLITE_PATH, ensure_dirs


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                transcript TEXT,
                crisis_type TEXT,
                urgency TEXT,
                summary_hi TEXT,
                steps_hi TEXT,
                sources TEXT,
                unknown INTEGER,
                filenames TEXT,
                language TEXT NOT NULL DEFAULT 'hi',
                document_issues TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(cases)")}
        if "language" not in columns:
            conn.execute("ALTER TABLE cases ADD COLUMN language TEXT NOT NULL DEFAULT 'hi'")
        if "document_issues" not in columns:
            conn.execute("ALTER TABLE cases ADD COLUMN document_issues TEXT NOT NULL DEFAULT '[]'")
        conn.commit()


def insert_case(
    transcript: str,
    crisis_type: str,
    urgency: str,
    summary_hi: str,
    steps_hi: list[str],
    sources: list[dict[str, str]],
    unknown: bool,
    filenames: list[str],
    language: str = "hi",
    document_issues: list[dict[str, str]] | None = None,
) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO cases (
                created_at, transcript, crisis_type, urgency,
                summary_hi, steps_hi, sources, unknown, filenames, language, document_issues
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                transcript,
                crisis_type,
                urgency,
                summary_hi,
                json.dumps(steps_hi, ensure_ascii=False),
                json.dumps(sources, ensure_ascii=False),
                1 if unknown else 0,
                json.dumps(filenames, ensure_ascii=False),
                "en" if language == "en" else "hi",
                json.dumps(document_issues or [], ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_cases(limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, crisis_type, summary_hi, language
            FROM cases
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_case(case_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["steps_hi"] = json.loads(data["steps_hi"] or "[]")
    data["sources"] = json.loads(data["sources"] or "[]")
    data["filenames"] = json.loads(data["filenames"] or "[]")
    data["document_issues"] = json.loads(data.get("document_issues") or "[]")
    data["unknown"] = bool(data["unknown"])
    return data
