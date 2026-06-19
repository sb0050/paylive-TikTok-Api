"""
Scraper PayLive : détecte les commandes "pl <ref>" en commentaire sous les
vidéos #paylive des boutiques, et les transmet au worker.

Réutilise la lib TikTokApi (fonctions `user.videos` / `video.comments`) : si
TikTok change et que le dépôt d'origine corrige la lib, un simple sync du fork
suffit — la logique métier PayLive (ce fichier) reste inchangée.
"""

import re
from datetime import datetime, timezone

from TikTokApi import TikTokApi

from . import config
from .browserless import browser_context_factory, close_browserless
from . import worker_client

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
        print(f"[paylive] @{handle} : vidéos KO ({e})")
        return orders

    tagged = [v for v in videos if _video_has_hashtag(v, config.PAYLIVE_HASHTAG)]
    tagged.sort(key=lambda v: getattr(v, "create_time", None) or 0, reverse=True)
    tagged = tagged[: config.RECENT_VIDEOS]
    print(f"[paylive] @{handle} : {len(tagged)} vidéo(s) #{config.PAYLIVE_HASHTAG}")

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
            print(f"[paylive] commentaires KO (video {v.id}) : {e}")
    return orders


async def scrape() -> None:
    handles = worker_client.fetch_targets()
    print(f"[paylive] {len(handles)} boutique(s) à scraper")
    if not handles:
        return
    if not config.MS_TOKENS:
        raise SystemExit("MS_TOKENS manquant")

    all_orders: list[dict] = []
    try:
        async with TikTokApi() as api:
            await api.create_sessions(
                num_sessions=1,
                ms_tokens=config.MS_TOKENS,
                sleep_after=3,
                browser_context_factory=browser_context_factory,
                timeout=config.NAV_TIMEOUT_MS,
                suppress_resource_load_types=_SUPPRESS,
            )
            print("[paylive] Session TikTokApi prête (Browserless)")
            for handle in handles:
                all_orders.extend(await _scrape_store(api, handle))
    finally:
        await close_browserless()

    print(f"[paylive] {len(all_orders)} commande(s) détectée(s)")
    if all_orders:
        res = worker_client.post_orders(all_orders)
        print(
            f"[paylive] Worker : {res.get('created', 0)} créé(s), "
            f"{res.get('skipped', 0)} ignoré(s)"
        )
