"""
Scraper PayLive : détecte les commandes "pl <ref>" en commentaire sous les
vidéos #paylive des boutiques, et les transmet au worker.

Réutilise la lib TikTokApi (fonctions `user.videos` / `video.comments`) : si
TikTok change et que le dépôt d'origine corrige la lib, un simple sync du fork
suffit — la logique métier PayLive (ce fichier) reste inchangée.
"""

import logging
import re
from datetime import datetime, timezone

from TikTokApi import TikTokApi

from . import config
from . import browserless_keys
from .browserless import browser_context_factory, close_browserless
from . import worker_client

log = logging.getLogger("paylive")

# Même pattern que le worker (cartCreator.ts / tiktokCommentCart.ts).
PAYLIVE_REGEX = re.compile(r"^\s*pl\s+(\S+)", re.IGNORECASE)

_SUPPRESS = ["image", "media", "font", "stylesheet"]


def _video_has_hashtag(video, tag: str) -> bool:
    d = getattr(video, "as_dict", None) or {}
    for ch in d.get("challenges") or []:
        if str(ch.get("title", "")).lower() == tag:
            return True
    for te in d.get("textExtra") or []:
        if str(te.get("hashtagName", "")).lower() == tag:
            return True
    return f"#{tag}" in str(d.get("desc", "")).lower()


def _comment_author(comment):
    u = (getattr(comment, "as_dict", None) or {}).get("user", {}) or {}
    return u.get("unique_id") or u.get("uniqueId"), u.get("nickname")


async def _scrape_store(api: TikTokApi, handle: str) -> list[dict]:
    """Renvoie les commandes détectées pour une boutique."""
    orders: list[dict] = []
    try:
        user = api.user(handle)
        videos = [v async for v in user.videos(count=config.VIDEOS_SCAN)]
    except Exception as e:  # boutique inaccessible / bloquée → on continue
        log.warning("@%s : récupération des vidéos KO (%s)", handle, e)
        return orders

    tagged = [v for v in videos if _video_has_hashtag(v, config.PAYLIVE_HASHTAG)]
    tagged.sort(key=lambda v: getattr(v, "create_time", None) or 0, reverse=True)
    tagged = tagged[: config.RECENT_VIDEOS]
    log.info(
        "@%s : %d vidéo(s) récupérée(s), %d avec #%s",
        handle,
        len(videos),
        len(tagged),
        config.PAYLIVE_HASHTAG,
    )

    store_orders = 0
    for v in tagged:
        post_url = f"https://www.tiktok.com/@{handle}/video/{v.id}"
        try:
            async for comment in api.video(id=v.id).comments(
                count=config.COMMENTS_PER_VIDEO
            ):
                text = getattr(comment, "text", "") or ""
                m = PAYLIVE_REGEX.match(text)
                if not m:
                    continue
                uid, nick = _comment_author(comment)
                if not uid:
                    continue
                ts = (getattr(comment, "as_dict", {}) or {}).get("create_time")
                created_at = (
                    datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                    if isinstance(ts, (int, float)) and ts
                    else None
                )
                store_orders += 1
                log.info(
                    "  commande: ref=%s par @%s sur %s", m.group(1), uid, post_url
                )
                orders.append(
                    {
                        "storeTiktokUsername": handle,
                        "videoId": str(v.id),
                        "postUrl": post_url,
                        "commentId": str(comment.id),
                        "authorUsername": str(uid),
                        "authorNickname": nick,
                        "text": text,
                        "ref": m.group(1),
                        "commentCreatedAt": created_at,
                    }
                )
        except Exception as e:
            log.warning("  commentaires KO (video %s) : %s", v.id, e)
    log.info("@%s : %d commande(s) détectée(s)", handle, store_orders)
    return orders


def _log_startup() -> None:
    log.info("=== Scraper PayLive — démarrage ===")
    log.info("WORKER_URL = %s", config.WORKER_URL or "(ABSENT)")
    log.info(
        "WORKER_INTERNAL_SECRET = %s",
        "défini" if config.WORKER_INTERNAL_SECRET else "(ABSENT)",
    )
    log.info(
        "BROWSERLESS = %s (rotation : %d token(s) ; seuil %d/%d)",
        "défini"
        if (
            config.BROWSERLESS_TOKENS
            or config.BROWSERLESS_WS
            or config.BROWSERLESS_TOKEN
        )
        else "(ABSENT)",
        len(config.BROWSERLESS_TOKENS),
        config.BROWSERLESS_USAGE_THRESHOLD,
        config.BROWSERLESS_USAGE_LIMIT,
    )
    log.info("MS_TOKENS = %d token(s)", len(config.MS_TOKENS))


async def _run_session(handles: list[str]) -> list[dict]:
    """Ouvre UNE session Browserless et scrape toutes les boutiques (1 tentative)."""
    orders: list[dict] = []
    try:
        async with TikTokApi() as api:
            log.info("Création de la session TikTokApi (Browserless)…")
            await api.create_sessions(
                num_sessions=1,
                ms_tokens=config.MS_TOKENS,
                sleep_after=3,
                browser_context_factory=browser_context_factory,
                timeout=config.NAV_TIMEOUT_MS,
                suppress_resource_load_types=_SUPPRESS,
            )
            log.info("Session TikTokApi prête.")
            for handle in handles:
                orders.extend(await _scrape_store(api, handle))
    finally:
        await close_browserless()
    return orders


async def scrape() -> None:
    _log_startup()
    # Vérif des env critiques AVANT tout appel réseau (message clair sinon).
    missing = [
        n
        for n, v in (
            ("WORKER_URL", config.WORKER_URL),
            ("WORKER_INTERNAL_SECRET", config.WORKER_INTERNAL_SECRET),
            ("MS_TOKENS", config.MS_TOKENS),
            (
                "BROWSERLESS_TOKENS/WS/TOKEN",
                config.BROWSERLESS_TOKENS
                or config.BROWSERLESS_WS
                or config.BROWSERLESS_TOKEN,
            ),
        )
        if not v
    ]
    if missing:
        raise RuntimeError(f"Variables d'environnement manquantes : {missing}")

    log.info("Récupération des boutiques auprès du worker…")
    handles = worker_client.fetch_targets()
    log.info("%d boutique(s) à scraper : %s", len(handles), handles)
    if not handles:
        log.info("Aucune boutique à scraper — fin.")
        return

    # Filet de sécurité : un token peut passer le seuil (ex. 850/1000) mais le run
    # consomme plus que le restant → 401 « usage limit » en pleine connexion. On
    # écarte alors ce token et on RELANCE le scrape avec le suivant.
    max_attempts = max(1, len(config.BROWSERLESS_TOKENS))
    all_orders: list[dict] = []
    for attempt in range(1, max_attempts + 1):
        try:
            all_orders = await _run_session(handles)
            break
        except Exception as e:
            if browserless_keys.is_usage_limit_error(e) and attempt < max_attempts:
                browserless_keys.mark_current_exhausted()
                log.warning(
                    "[browserless] quota épuisé pendant le run (%s) — "
                    "nouvelle tentative %d/%d avec le token suivant",
                    str(e).splitlines()[0] if str(e) else e,
                    attempt + 1,
                    max_attempts,
                )
                continue
            raise

    log.info("Total : %d commande(s) détectée(s)", len(all_orders))
    if all_orders:
        log.info("Envoi au worker…")
        res = worker_client.post_orders(all_orders)
        log.info(
            "Worker : %s créé(s), %s ignoré(s)",
            res.get("created", 0),
            res.get("skipped", 0),
        )
    else:
        log.info("Rien à envoyer au worker.")
