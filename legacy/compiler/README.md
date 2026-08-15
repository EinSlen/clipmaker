# Compilateur historique

Ce dossier conserve l'ancien pipeline Python de compilation de clips Twitch. Il n'est plus utilisé
par l'application web, Docker ou l'orchestrateur quotidien. Les fichiers ont été regroupés ici pour
garder leur fonctionnement relatif (`main.py`, police, son et dépendances) sans encombrer la racine.

Pour un nouveau déploiement, utiliser le studio dans `web/` et `docker-compose.yml`. Ce pipeline est
archivé et n'est plus couvert par les tests de production.
