"""Client HTTP minimal (stdlib) vers le worker PayLive (auth x-internal-secret)."""

import json
import urllib.request
import urllib.error

from . import config


def _request(path: str, method: str = "GET", body: dict | None = None) -> dict:
    url = f"{config.require('WORKER_URL', config.WORKER_URL)}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "x-internal-secret": config.require(
                "WORKER_INTERNAL_SECRET", config.WORKER_INTERNAL_SECRET
            ),
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8") or "{}"
        return json.loads(raw)


def fetch_targets() -> list[str]:
    """@handles des boutiques à scraper (sans @)."""
    data = _request("/internal/tiktok-scrape-targets")
    return [
        str(t.get("tiktokUsername", "")).lstrip("@").strip()
        for t in (data.get("targets") or [])
        if str(t.get("tiktokUsername", "")).strip()
    ]


def post_orders(orders: list[dict]) -> dict:
    """Envoie le batch de commandes détectées au worker."""
    return _request("/internal/tiktok-comment-order", "POST", {"orders": orders})
