"""
Rotation des tokens Browserless — pendant Python d'euler_api_keys / keyManager.ts
(côté worker), mais sans table ni Redis : les tokens vivent dans l'env
(`BROWSERLESS_TOKENS`, séparés par des virgules) et le quota est MENSUEL, remis à
zéro par Browserless en début de mois.

On ne se base donc PAS sur une date de création mais sur la CONSOMMATION RÉELLE,
lue en direct via l'API Browserless :

    GET https://api.browserless.io/v1/account/usage?token=<token>

Stratégie « fill-first » : on parcourt les tokens dans l'ordre de l'env et on
prend le PREMIER dont la conso est sous le seuil (par défaut 900/1000). Quand le
token 1 dépasse 900, on bascule sur le 2, etc. Chaque token = un compte
Browserless distinct (son propre quota).

Repli : si `BROWSERLESS_TOKENS` est vide → l'appelant retombe sur le token/URL de
l'env historique (`BROWSERLESS_TOKEN` / `BROWSERLESS_WS`).
"""

import logging
from typing import NamedTuple

import requests

from . import config
from . import usage_store

log = logging.getLogger("paylive")

USAGE_ENDPOINT = "https://api.browserless.io/v1/account/usage"

# --- État de run (rotation à chaud) ---------------------------------------
# Tokens écartés PENDANT le run courant (ex. 401 « usage limit » à la connexion,
# ou token invalide) : select_token() les saute → la relance prend le suivant.
_excluded: set[str] = set()
# Dernier token retourné par select_token() → cible de mark_current_exhausted().
_last_selected: str | None = None


def is_usage_limit_error(exc: BaseException) -> bool:
    """Vrai si l'exception ressemble à un quota Browserless épuisé (401)."""
    msg = str(exc).lower()
    return (
        "usage limit" in msg
        or "upgrade to a paid plan" in msg
        or "401" in msg
        or "unauthorized" in msg
    )


def mark_current_exhausted() -> None:
    """
    Écarte le dernier token sélectionné pour le reste du run (il ne sera plus
    proposé) et le marque saturé dans le cache (les runs suivants le sauteront
    aussi jusqu'au reset de période — l'API restant la source de vérité).
    """
    global _last_selected
    if not _last_selected:
        return
    _excluded.add(_last_selected)
    try:
        usage_store.remember(_last_selected, float(config.BROWSERLESS_USAGE_LIMIT))
    except Exception:
        pass
    log.warning("[browserless] token %s… écarté (saturé)", _last_selected[:6])
    _last_selected = None


class UsageInfo(NamedTuple):
    used: float | None  # unités consommées sur la période de facturation courante
    included: float | None  # quota de la période (ex. 1000)
    remaining: float | None  # restant (ex. 58)
    period_end: str | None  # fin de la période de facturation (ISO), pour le cache


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def _parse_usage(payload) -> UsageInfo:
    """
    Parse la réponse de /v1/account/usage.

    Forme réelle (2026-07) :
      {"plan":{…},
       "units":{"included":1000,"used":942,"remaining":58},
       "billingPeriod":{"start":"…","end":"…"}}

    On reste défensif (champ configurable + fallbacks) au cas où le format évolue.
    """
    if isinstance(payload, (int, float)):
        return UsageInfo(float(payload), None, None, None)
    if not isinstance(payload, dict):
        return UsageInfo(None, None, None, None)

    used = included = remaining = None
    period_end = None

    units = payload.get("units")
    if isinstance(units, dict):
        used = _num(units.get("used"))
        included = _num(units.get("included"))
        remaining = _num(units.get("remaining"))
        # Dérive used = included - remaining si "used" absent.
        if used is None and included is not None and remaining is not None:
            used = included - remaining
    elif isinstance(units, (int, float)):
        used = float(units)

    # Fallbacks top-level (champ configurable en priorité) si "units.used" absent.
    if used is None:
        for k in (
            config.BROWSERLESS_USAGE_FIELD,
            "used",
            "unitsUsed",
            "consumed",
            "usage",
            "total",
            "count",
        ):
            if k and isinstance(payload.get(k), (int, float)):
                used = float(payload[k])
                break

    bp = payload.get("billingPeriod")
    if isinstance(bp, dict) and isinstance(bp.get("end"), str):
        period_end = bp["end"]

    return UsageInfo(used, included, remaining, period_end)


def fetch_usage(token: str) -> UsageInfo:
    """Conso courante d'un token via l'API Browserless (UsageInfo tout-None si KO)."""
    try:
        resp = requests.get(USAGE_ENDPOINT, params={"token": token}, timeout=30)
        resp.raise_for_status()
        return _parse_usage(resp.json())
    except Exception as e:  # réseau / HTTP / JSON → conso inconnue
        log.warning("[browserless] usage KO pour %s… (%s)", token[:6], e)
        return UsageInfo(None, None, None, None)


def select_token() -> str | None:
    """
    Choisit le 1er token dont la conso mensuelle < seuil (fill-first).

    Retourne None si `BROWSERLESS_TOKENS` est vide (→ repli env par l'appelant)
    OU si tous les tokens sont saturés (dans ce cas on log un warning et on
    retombe aussi sur l'env, faute de mieux).
    """
    global _last_selected

    tokens = config.BROWSERLESS_TOKENS
    if not tokens:
        return None

    threshold = config.BROWSERLESS_USAGE_THRESHOLD
    limit = config.BROWSERLESS_USAGE_LIMIT

    for token in tokens:
        # Token déjà écarté pendant ce run (401 / saturé) → on saute.
        if token in _excluded:
            continue
        # 1) API = source de vérité. 2) repli sur le cache volume (dernière conso
        #    connue sur la période courante). 3) sinon inconnue.
        info = fetch_usage(token)
        used = info.used
        source = "api"
        if used is not None:
            usage_store.remember(token, used, info.period_end)  # rafraîchit le cache
        else:
            used = usage_store.get_cached(token)
            source = "cache"

        # Conso toujours inconnue (API KO + pas de cache) → on tente ce token
        # plutôt que de tout bloquer : mieux vaut un run qu'aucun run du tout.
        if used is None:
            log.info("[browserless] token %s… conso inconnue → utilisé", token[:6])
            _last_selected = token
            return token
        if used < threshold:
            log.info(
                "[browserless] token %s… conso=%.0f/%d (seuil %d, src=%s) → CHOISI",
                token[:6],
                used,
                limit,
                threshold,
                source,
            )
            _last_selected = token
            return token
        log.info(
            "[browserless] token %s… conso=%.0f/%d (seuil %d, src=%s) → SATURÉ, suivant",
            token[:6],
            used,
            limit,
            threshold,
            source,
        )

    log.warning(
        "[browserless] les %d token(s) sont saturés (>= %d) — repli env",
        len(tokens),
        threshold,
    )
    return None
