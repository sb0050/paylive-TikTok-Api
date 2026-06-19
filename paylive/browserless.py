"""
Connexion au navigateur distant Browserless (proxy résidentiel) pour TikTokApi.

⚠ On utilise connect_over_cdp (protocole CDP, tolérant aux versions playwright),
PAS connect() (protocole Playwright) qui exige client==serveur (KeyError 'error').
Le retour de la factory est utilisé DIRECTEMENT comme contexte par TikTokApi
(tiktok.py:338-339) → on retourne un BrowserContext.
"""

import re
from urllib.parse import quote

from playwright.async_api import Playwright, BrowserContext

from . import config

_browser = None  # référence pour fermer la connexion CDP en fin de run


def build_ws() -> str:
    if config.BROWSERLESS_WS:
        return config.BROWSERLESS_WS
    token = config.require("BROWSERLESS_TOKEN", config.BROWSERLESS_TOKEN)
    # Endpoint CDP de BASE (pas /chrome/playwright ni /stealth).
    return (
        f"wss://production-sfo.browserless.io?token={quote(token)}"
        f"&proxy=residential&proxyCountry={config.PROXY_COUNTRY}&proxySticky=true"
    )


async def browser_context_factory(p: Playwright) -> BrowserContext:
    global _browser
    ws = build_ws()
    safe = re.sub(r"token=[^&]+", "token=***", ws)
    print(f"[paylive] Connexion Browserless (CDP) -> {safe}")
    _browser = await p.chromium.connect_over_cdp(ws)
    return (
        _browser.contexts[0]
        if _browser.contexts
        else await _browser.new_context()
    )


async def close_browserless() -> None:
    global _browser
    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
