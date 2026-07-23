# Dockerfile dédié au scraper PayLive (cron Railway).
#
# Python 3.12 (l'image upstream playwright:focal est en 3.8 → trop vieux pour
# TikTokApi et pour notre syntaxe list[...] / X | None).
#
# Léger : PAS de navigateur local (on se connecte à Browserless distant via CDP)
# → inutile de faire `playwright install`.
#
# `pip install .` installe le FORK lui-même + TOUTES ses dépendances déclarées
# (proxyproviders, playwright, etc.) → on évite les ModuleNotFoundError. Le code
# du fork est aussi copié tel quel, donc `import TikTokApi` reste aligné sur la
# version synchronisée.
#
# Railway : "Dockerfile Path" = `paylive/Dockerfile`, puis un Cron Schedule
# (ex. `0 2 * * *`). Le CMD ci-dessous évite d'avoir à définir un Start Command.

FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir . proxyproviders python-dotenv

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "paylive"]
