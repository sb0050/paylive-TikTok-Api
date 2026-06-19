"""Configuration (env) du scraper PayLive."""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optionnel en prod (env Railway déjà injecté)
    pass

# --- Worker PayLive (source des boutiques + destination des commandes) ---
WORKER_URL = os.getenv("WORKER_URL", "").rstrip("/")
WORKER_INTERNAL_SECRET = os.getenv("WORKER_INTERNAL_SECRET", "")

# --- Browserless (navigateur distant + proxy résidentiel) ---
BROWSERLESS_WS = os.getenv("BROWSERLESS_WS", "").strip()
BROWSERLESS_TOKEN = os.getenv("BROWSERLESS_TOKEN", "").strip()
PROXY_COUNTRY = os.getenv("PROXY_COUNTRY", "fr").strip()

# --- ms_token (rotation) ---
MS_TOKENS = [t.strip() for t in os.getenv("MS_TOKENS", "").split(",") if t.strip()]

# --- Paramètres de scraping ---
PAYLIVE_HASHTAG = os.getenv("PAYLIVE_HASHTAG", "paylive").lower().lstrip("#")
RECENT_VIDEOS = int(os.getenv("RECENT_VIDEOS", "10"))
VIDEOS_SCAN = int(os.getenv("VIDEOS_SCAN", "30"))
COMMENTS_PER_VIDEO = int(os.getenv("COMMENTS_PER_VIDEO", "50"))
NAV_TIMEOUT_MS = int(os.getenv("NAV_TIMEOUT_MS", "90000"))


def require(name: str, value: str) -> str:
    if not value:
        raise SystemExit(f"Variable d'environnement manquante : {name}")
    return value
