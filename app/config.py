"""PadhaiSetu configuration. All settings env-overridable; TZ is Asia/Kolkata everywhere."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

PORT = int(os.environ.get("PORT", "8831"))
HOST = os.environ.get("HOST", "0.0.0.0")

DB_PATH_ENV_VAR = "PADHAISETU_DB"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "padhaisetu.db"


def db_path() -> str:
    """Resolve DB path lazily so tests can redirect it via env var."""
    return os.environ.get(DB_PATH_ENV_VAR) or str(DEFAULT_DB_PATH)

TZ_NAME = os.environ.get("TZ", "Asia/Kolkata")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "padhaisetu-verify")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
GRAPH_API_BASE = os.environ.get("GRAPH_API_BASE", "https://graph.facebook.com/v20.0")
