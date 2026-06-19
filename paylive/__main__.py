"""
Point d'entrée du scraper PayLive (lancé 1×/jour à 2h par le cron Railway).

    python -m paylive
"""

import asyncio

from .scraper import scrape

if __name__ == "__main__":
    asyncio.run(scrape())
