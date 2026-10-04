import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
STORE_PATH = DATA_DIR / "store.json"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3.8-flash").split(",") if m.strip()]
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts").strip()
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Achird").strip()
# Empty means anyone may register as a teacher (fine for local demos).
TEACHER_INVITE_CODE = os.getenv("TEACHER_INVITE_CODE", "").strip()


def gemini_enabled() -> bool:
    return bool(GEMINI_API_KEY)
