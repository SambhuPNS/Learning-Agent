import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
STORE_PATH = DATA_DIR / "store.json"

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts").strip()
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Achird").strip()
# Empty means anyone may register as a teacher (fine for local demos).
TEACHER_INVITE_CODE = os.getenv("TEACHER_INVITE_CODE", "").strip()
FIRESTORE_ENABLED = os.getenv("FIRESTORE_ENABLED", "").strip().lower() in {"1", "true", "yes"}
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
VERTEX_AI_LOCATION = os.getenv("VERTEX_AI_LOCATION", "global").strip()


def gemini_enabled() -> bool:
    return bool(GOOGLE_CLOUD_PROJECT)
