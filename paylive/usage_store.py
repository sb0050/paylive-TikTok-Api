"""
Cache de consommation Browserless sur volume (OPT-IN) — repli si l'API usage est
indisponible/illisible. **L'API reste la source de vérité** ; ce cache ne fait que
mémoriser la dernière conso connue par token, valable jusqu'à la fin de la période
de facturation Browserless (`billingPeriod.end`, cf. réponse de l'API usage — ce
n'est PAS le mois calendaire mais un cycle ancré sur la date du compte).

Persistance : un simple fichier JSON, chemin dans `BROWSERLESS_STATE_FILE`
(ex. `/data/browserless_usage.json` sur un volume Railway → survit aux runs ET
aux redéploiements). Vide/non monté → no-op (dégradation silencieuse).

Sécurité : on n'écrit PAS le token en clair — clé = SHA-256 tronqué du token.
"""

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

from . import config

log = logging.getLogger("paylive")


def _enabled() -> bool:
    return bool(config.BROWSERLESS_STATE_FILE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _parse_iso(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _load_tokens() -> dict:
    path = config.BROWSERLESS_STATE_FILE
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tokens = data.get("tokens") if isinstance(data, dict) else None
        return tokens if isinstance(tokens, dict) else {}
    except Exception as e:
        log.warning("[browserless] cache conso illisible (%s)", e)
        return {}


def _entry_valid(entry: dict) -> bool:
    """L'entrée est-elle encore dans la période de facturation ?"""
    pe = entry.get("period_end")
    if isinstance(pe, str):
        end = _parse_iso(pe)
        if end is not None:
            return _now() < end  # période non terminée → conso encore valable
        return False
    # Pas de period_end fiable → repli prudent sur le mois calendaire via "at".
    at = entry.get("at")
    return isinstance(at, str) and at[:7] == _now().strftime("%Y-%m")


def get_cached(token: str) -> float | None:
    """Dernière conso connue du token si la période courante n'est pas terminée."""
    if not _enabled():
        return None
    entry = _load_tokens().get(_token_key(token))
    if not isinstance(entry, dict) or not isinstance(entry.get("units"), (int, float)):
        return None
    return float(entry["units"]) if _entry_valid(entry) else None


def remember(token: str, units: float, period_end: str | None = None) -> None:
    """Mémorise (best-effort) la conso `units` du token + fin de période."""
    if not _enabled():
        return
    tokens = _load_tokens()
    tokens[_token_key(token)] = {
        "units": float(units),
        "period_end": period_end,
        "at": _now().isoformat(),
    }
    path = config.BROWSERLESS_STATE_FILE
    try:
        parent = os.path.dirname(path) or "."
        os.makedirs(parent, exist_ok=True)
        # Écriture atomique (tmp + os.replace) → pas de fichier corrompu.
        fd, tmp = tempfile.mkstemp(dir=parent, prefix=".usage_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"tokens": tokens}, f)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    except Exception as e:
        log.warning("[browserless] cache conso non écrit (%s)", e)
