"""
Code spécifique PayLive ajouté au fork TikTok-Api.

Isolé dans ce package `paylive/` pour NE PAS entrer en conflit lors du sync avec
le dépôt d'origine (davidteather/TikTok-Api) : on ne touche pas aux fichiers
upstream, on réutilise juste la lib `TikTokApi`.

Détecte les prises de commande "pl <ref>" laissées en commentaire sous les
vidéos #paylive des boutiques et les transmet au worker PayLive.
"""
