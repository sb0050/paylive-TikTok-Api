"""Configuration (env) du scraper PayLive."""

import os
import re

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
# Rotation : plusieurs tokens séparés par des virgules (~1000 unités/mois chacun,
# reset mensuel côté Browserless). On sélectionne « fill-first » selon la conso
# RÉELLE lue via l'API Browserless (cf. browserless_keys.py), pas selon une date.
# ⚠ Ce sont les TOKENS BRUTS (pas des URLs). Tolérant quand même : si une valeur
# est une URL (…?token=XXX&…), on en extrait le token.
def _extract_token(raw: str) -> str:
    raw = raw.strip()
    if "token=" in raw:
        m = re.search(r"token=([^&\s]+)", raw)
        if m:
            return m.group(1)
    return raw


BROWSERLESS_TOKENS = [
    _extract_token(t) for t in os.getenv("BROWSERLESS_TOKENS", "").split(",") if t.strip()
]
# Seuil de bascule : au-delà de THRESHOLD unités consommées sur LIMIT, on passe
# au token suivant.
BROWSERLESS_USAGE_LIMIT = int(os.getenv("BROWSERLESS_USAGE_LIMIT", "1000"))
BROWSERLESS_USAGE_THRESHOLD = int(os.getenv("BROWSERLESS_USAGE_THRESHOLD", "900"))
# Nom du champ « unités consommées » dans la réponse de l'API usage (au cas où
# Browserless le nomme différemment) — laissé vide = détection automatique.
BROWSERLESS_USAGE_FIELD = os.getenv("BROWSERLESS_USAGE_FIELD", "").strip()
# Fichier de cache de conso (OPT-IN) : chemin sur un volume Railway persistant
# (ex. /data/browserless_usage.json). Sert UNIQUEMENT de repli si l'API usage est
# indisponible/illisible — l'API reste la source de vérité. Vide = désactivé.
BROWSERLESS_STATE_FILE = os.getenv("BROWSERLESS_STATE_FILE", "").strip()
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
    # RuntimeError (et pas SystemExit) → capté par le try/except de __main__ et
    # loggé avec un message clair (sinon l'erreur passe inaperçue sur Railway).
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante : {name}")
    return value
