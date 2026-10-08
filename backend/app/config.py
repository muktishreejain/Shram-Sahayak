from pathlib import Path

from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")
load_dotenv(BACKEND / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

DATA_DIR = BACKEND / "data"
UPLOADS_DIR = BACKEND / "uploads"
KNOWLEDGE_DIR = BACKEND / "knowledge"
CHROMA_DIR = DATA_DIR / "chroma"
SQLITE_PATH = DATA_DIR / "app.db"

COLLECTION_NAME = "worker_help"
EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_TEXT_CHARS = 16000

ALLOWLIST = [
    "https://samadhan.labour.gov.in/",
    "https://eshram.gov.in/",
    "https://www.myscheme.gov.in/",
    "https://shramsuvidha.gov.in/",
    "https://ncs.gov.in/",
    "https://locator.csc.gov.in/",
]

CRISIS_TYPES = {
    "unpaid_wages",
    "illegal_termination",
    "workplace_injury",
    "harassment",
    "documents_missing",
    "other",
}

URGENCY_TYPES = {"low", "medium", "high", "critical"}

GEMINI_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
]


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
