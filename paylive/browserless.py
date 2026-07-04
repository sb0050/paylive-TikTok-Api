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
from . import browserless_keys

_browser = None  # référence pour fermer la connexion CDP en fin de run


def _ws_from_token(token: str) -> str:
    # Endpoint CDP de BASE (pas /chrome/playwright ni /stealth).
    return (
        f"wss://production-sfo.browserless.io?token={quote(token)}"
        f"&proxy=residential&proxyCountry={config.PROXY_COUNTRY}&proxySticky=true"
    )


def build_ws() -> str:
    # 1) Rotation : 1er token sous le seuil de conso mensuelle (fill-first).
    token = browserless_keys.select_token()
    if token:
        return _ws_from_token(token)
    # Si des tokens sont configurés mais qu'aucun n'est disponible (tous saturés
    # ou écartés en cours de run), on échoue clairement plutôt que de retomber sur
    # un repli env trompeur.
    if config.BROWSERLESS_TOKENS:
        raise RuntimeError(
            "Tous les tokens Browserless sont saturés ou écartés "
            "(quota mensuel atteint) — ajouter un token ou attendre le reset."
        )
    # 2) Repli env (aucun BROWSERLESS_TOKENS configuré) : URL WS complète…
    if config.BROWSERLESS_WS:
        return config.BROWSERLESS_WS
    # 3) …ou token unique historique.
    token = config.require("BROWSERLESS_TOKEN", config.BROWSERLESS_TOKEN)
    return _ws_from_token(token)


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
