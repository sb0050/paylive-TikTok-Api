# paylive/ — scraper de commandes par commentaire TikTok

Code spécifique PayLive ajouté au fork (isolé ici pour ne pas gêner le sync upstream).
Détecte `pl <ref>` dans les commentaires des vidéos #paylive des boutiques et POST les
commandes au worker PayLive (qui crée les paniers).

## Flux
1. `GET {WORKER_URL}/internal/tiktok-scrape-targets` → @handles des boutiques (order-taking actif).
2. Connexion Browserless (CDP, proxy résidentiel) ; pour chaque boutique : `user.videos`
   → filtre `#paylive` → 10 plus récentes → `video.comments` → regex `pl <ref>`.
3. `POST {WORKER_URL}/internal/tiktok-comment-order` (batch) → worker (dédup par `comment_id`,
   création du panier + `from_tiktok_post_url`).

## Lancer en local
```sh
pip install -r requirements.txt python-dotenv   # requirements du fork + dotenv
cp paylive/.env.example .env
python -m paylive
```
(Réutilise la lib `TikTokApi` du dépôt — pas de réécriture de la logique de scraping.)

## Déploiement Railway (projet séparé, déjà créé)
- **Start command** : `python -m paylive`
- **Cron Schedule** : `0 2 * * *`  → ~04:00 Paris (heure d'été, UTC+2).
  (Railway exécute le cron en **UTC** : 4h Paris = 2h UTC l'été, 3h UTC l'hiver → `0 3 * * *`.)
- Variables d'env : cf. `paylive/.env.example`.
- Pas besoin de `playwright install` (navigateur distant Browserless).
