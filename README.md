# 🌊 Nami — Service Self-Hosted Anime Streaming & Téléchargement

> **Service unifié et autonome pour rechercher, regarder à la volée (streaming direct M3U8) et télécharger vos animes préférés sur disque externe**, propulsé par [YoitsuWrap](https://github.com/TMCooper/YoitsuWrap), [AnimeSamaApi](https://github.com/TMCooper/AnimeSamaApi) et [VoirAnime_API](https://github.com/TMCooper/voiranime_API). Conçu pour être **léger, sobre, esthétique et optimisé pour tourner sur Raspberry Pi ou mini-PC**.

---

## ✨ Fonctionnalités Clés

- 📺 **Visionnage à la volée & Lecture locale** :
  - **Streaming direct M3U8 / MP4** résolu à la volée via proxy CORS intégré.
  - **Lecture ultra-rapide des fichiers téléchargés hors Docker** grâce au protocole HTTP 206 Partial Content (Range requests) : reprise et recherche instantanées dans la vidéo sans surcharger le processeur du Raspberry Pi.
- 💾 **Stockage hors du conteneur Docker** :
  - Les épisodes téléchargés sont rangés directement sur votre disque dur externe ou dossier local (`/downloads`), utilisables par n'importe quel lecteur multimédia (VLC, Plex, Jellyfin...).
- ⚡ **Catalogue incrémental & Découvertes aléatoires** :
  - La page d'accueil s'incrémente intelligemment de vos recherches et visionnages.
  - Section **"Continuer la lecture"** avec barre de progression exacte, badge de saison/épisode et reprise en 1 clic.
  - Section **"Découvertes & Aléatoire"** pour explorer de nouveaux animes immédiatement.
  - Section **"Médiathèque Locale Hors-Ligne"** pour regarder vos animes téléchargés même sans Internet.
- 📊 **Système multi-utilisateurs & Statistiques détaillées** :
  - Profils avec avatars personnalisés.
  - Tracking du temps total de visionnage (heures & minutes).
  - Nombre d'épisodes et de séries complétées.
  - Calcul en direct de l'espace disque occupé par vos téléchargements.
- 🚀 **Système de Cache JSON intelligent** :
  - Les détails d'animes et listes d'épisodes sont mis en cache localement dans `data/cache/` pour éviter de surcharger les APIs et offrir une vitesse de chargement instantanée.
  - Bouton **"Actualiser"** pour forcer la mise à jour quand un nouvel épisode sort.
- 🐳 **Prêt pour Docker & Docker Compose (Multi-Arch : PC x86 & Raspberry Pi ARM64)** :
  - Finis les sous-modules Git instables : tout est embarqué et démarre en une seule commande.

---

## 🛠️ Démarrage Rapide

### 1. Avec Docker Compose (Recommandé pour Raspberry Pi & Serveurs)

```bash
docker compose up -d --build
```

L'application est immédiatement accessible sur :
```
http://<IP_DE_VOTRE_MACHINE>:8070
```
*(ou sur le port 8080 en direct)*.

#### 📁 Configuration des disques externes (`docker-compose.yml`)

Par défaut, les volumes sont montés dans le dossier du projet :
```yaml
volumes:
  - ./data:/app/data                # Base de données, utilisateurs, historique & cache
  - ./downloads:/downloads          # Dossier des vidéos téléchargées
```

Pour enregistrer vos vidéos sur un **disque dur externe** branché à votre Raspberry Pi ou PC (ex: disque monté sur `/media/pi/MonDisque`), modifiez simplement la ligne du volume :
```yaml
volumes:
  - ./data:/app/data
  - /media/pi/MonDisque/animes:/downloads
```

---

### 2. Lancement Local sans Docker (Mode Développement)

#### Prérequis
- Python 3.10+
- Node.js 18+ (pour le frontend)
- FFmpeg installé sur le système

#### Backend :
```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

#### Frontend :
```bash
cd frontend
npm install
npm run dev
```

#### Tests (backend) :
```bash
pip install pytest flask
python -m pytest
```
Les tests n'écrivent que dans des dossiers temporaires (jamais dans `data/`).

#### Journaux des APIs :
Les sorties d'AnimeSamaApi et de VoirAnime_API sont dans `data/logs/animesama.log` et `data/logs/voiranime.log` (le lancement précédent est conservé en `.log.1`).

---

## 🏗️ Architecture du Projet

```
Nami/
├── backend/
│   ├── main.py                     # Serveur FastAPI principal + orchestration des sous-services
│   ├── routers/
│   │   ├── api.py                  # Endpoints REST (Catalogue, stream local HTTP 206, stats, auth)
│   │   └── stream_proxy.py         # Proxy HLS / M3U8 pour contourner les blocages CORS et headers
│   └── services/
│       ├── catalog_service.py      # Recherche multi-sources, résolution de liens & détails
│       ├── cache_service.py        # Gestion du cache JSON & scan du disque local
│       ├── download_service.py     # File d'attente asynchrone FFmpeg / HTTP
│       ├── history_service.py      # Tracking par utilisateur, reprise exacte & statistiques
│       ├── settings_service.py     # Configuration du stockage et options
│       └── user_service.py         # Gestion des comptes et profils
├── frontend/                       # Interface React + Vite (Vanilla CSS moderne, thème sombre)
│   ├── src/
│   │   ├── components/
│   │   │   ├── VideoPlayerModal.jsx     # Lecteur custom (M3U8 & Local, raccourcis, reprise auto)
│   │   │   ├── OfflineLibraryView.jsx   # Vue médiathèque locale hors-ligne
│   │   │   ├── StatsModal.jsx           # Modal des statistiques de visionnage
│   │   │   ├── AnimeDetailModal.jsx     # Fiche anime avec détection des épisodes téléchargés
│   │   │   ├── CatalogGrid.jsx          # Grille d'accueil avec étagères dynamiques
│   │   │   └── Header.jsx               # Navigation, recherche et switch de profil
├── AnimeSamaApi/                   # Moteur API Anime-Sama
├── voiranime_API/                  # Moteur API VoirAnime
├── data/                           # Données persistantes (utilisateurs, historique, cache)
├── downloads/                      # Dossier hôte des épisodes téléchargés
├── Dockerfile                      # Image multi-plateforme légère
└── docker-compose.yml              # Déploiement en 1 clic
```

---

## 🔄 Mises à Jour & Maintenance

### 1. Directement depuis l'application Web (Recommandé)
Ouvrez l'icône **⚙️ Paramètres** en haut à droite :
- Une section dédiée vérifie automatiquement l'état des versions de **AnimeSamaApi**, **VoirAnime_API** et **YoitsuWrap**.
- Vous pouvez mettre à jour chaque composant individuellement ou cliquer sur **« Tout mettre à jour »**.
- Le serveur recharge automatiquement les processus en tâche de fond.
- **Sécurité des données garantie :** Aucun fichier utilisateur, historique ni téléchargement n'est modifié ou supprimé.

### 2. Via les scripts de reconstruction
Pour reconstruire proprement le conteneur Docker après de grosses modifications sans toucher à vos données :
- **Sous Windows** : Double-cliquez sur `rebuild.bat`
- **Sous Linux / Raspberry Pi** : Exécutez `./rebuild.sh`

---

## ⌨️ Raccourcis Clavier du Lecteur Vidéo

| Touche | Action |
|---|---|
| `Espace` | Lecture / Pause |
| `←` / `→` | Reculer / Avancer de 10 secondes |
| `↑` / `↓` | Augmenter / Baisser le volume |
| `F` | Basculer en Plein Écran |
| `M` | Couper / Réactiver le son |

---

## 📄 Licence

Ce projet est sous licence [GPL v3](LICENSE).
Propulsé avec ❤️ par les wrappers et APIs de TMCooper.