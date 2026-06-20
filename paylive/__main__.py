"""
Point d'entrée du scraper PayLive (lancé 1×/jour par le cron Railway).

    python -m paylive

Logs forcés sur stdout (StreamHandler → flush par ligne) pour qu'ils
apparaissent bien dans Railway, même en conteneur (stdout bufferisé sinon).
"""

import asyncio
import logging
import sys

from .scraper import scrape


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )


if __name__ == "__main__":
    _setup_logging()
    log = logging.getLogger("paylive")
    try:
        asyncio.run(scrape())
        log.info("Job terminé avec succès.")
    except Exception:
        # Traceback complet → on voit ENFIN pourquoi le run échoue sur Railway.
        log.exception("Job en échec")
        sys.exit(1)
