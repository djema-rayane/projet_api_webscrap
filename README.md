# Amazon Reviews Scraper & AI Analysis

Système complet de scraping d'avis Amazon avec analyse de sentiment IA et génération automatique de réponses professionnelles.

---

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Démarrage rapide](#démarrage-rapide)
- [Utilisation détaillée](#utilisation-détaillée)
- [API Endpoints](#api-endpoints)
- [Structure du projet](#structure-du-projet)
- [Configuration](#configuration)
- [Dépannage](#dépannage)

---

## Fonctionnalités

**Scraping multi-sources**
- Amazon (mode simple, URL directe, authentifié)
- TrustPilot
- Yelp

**Analyse IA**
- Analyse de sentiment (positif/neutre/négatif)
- Génération automatique de réponses professionnelles
- Support GPU pour accélération

**Base de données**
- Stockage SQLite local
- Traçabilité complète des sessions
- Export CSV/JSON

---

## Prérequis

**Obligatoire**
- Python 3.13 ou supérieur
- Chrome/Chromium installé
- UV (gestionnaire de paquets)

**Optionnel**
- CUDA pour accélération GPU
- Compte Amazon pour scraping authentifié

---

## Installation

### 1. Cloner le projet
```bash
git clone <git@github.com:djema-rayane/projet_api_webscrap.git>
```

### 2. Installer UV

```bash
pip install uv
```

### 3. Installer les dépendances
```bash
uv sync
```

Cette commande va :
- Créer un environnement virtuel automatiquement
- Installer toutes les dépendances du projet
- Télécharger les modèles nécessaires

---

## Démarrage rapide

### 1. Lancer l'API
```bash
cd app
uv run uvicorn app.main:app --reload
```

Au premier lancement, la base de données se crée automatiquement dans `data/avis_scraping.db`.

**Console :**
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
Base de données initialisée : /home/user/project/data/avis_scraping.db
```

### 2. Accéder à la documentation

Ouvrir dans le navigateur :
- **Swagger UI** : http://localhost:8000/docs

### 3. Premier scraping (exemple simple)

**Requête via Swagger UI :**
```
POST /scrape
```

**Body :**
```json
{
  "mode": "url_auth",
  "product_url": "https://www.amazon.fr/dp/B0XXXXXX",
  "username": "votre-email@amazon.fr",
  "password": "votre-mot-de-passe",
  "limit_per_product": 50,
  "france_only": true,
  "headless": true
}
```

**Réponse :**
```json
{
  "task_id": "cf6e0af1-d2c4-41e9-8f4e-c8fbbe7500bc",
  "status": "pending",
  "message": "Scraping lancé en mode url_auth",
  "mode": "url_auth"
}
```

### 4. Suivre l'avancement
```
GET /tasks/{task_id}
```

**Réponse :**
```json
{
  "task_id": "cf6e0af1-d2c4-41e9-8f4e-c8fbbe7500bc",
  "status": "completed",
  "progress": "Terminé : 50 avis insérés en temps réel dans la BDD",
  "started_at": "2026-01-30 23:29:14",
  "completed_at": "2026-01-30 23:35:42"
}
```

---

## Utilisation détaillée

### Workflow complet
```
1. Scraping      → Récupération des avis Amazon
2. Sentiment     → Analyse du sentiment (positif/neutre/négatif)
3. Réponses      → Génération de réponses professionnelles
4. Export        → CSV/JSON des résultats
```

---

### Étape 1 : Scraping des avis

**Mode URL authentifié (recommandé pour plus de 10 avis)**
```bash
POST /scrape
```
```json
{
  "mode": "url_auth",
  "product_url": "https://www.amazon.fr/dp/B0XXXXXX",
  "username": "email@amazon.fr",
  "password": "mot-de-passe",
  "limit_per_product": 50,
  "france_only": true,
  "headless": true,
  "cookies_only": false
}
```

**Paramètres :**
- `mode` : Type de scraping (`url_auth` recommandé)
- `product_url` : URL du produit Amazon
- `username` : Email de connexion Amazon
- `password` : Mot de passe Amazon
- `limit_per_product` : Nombre maximum d'avis à récupérer
- `france_only` : Filtrer uniquement les avis français
- `headless` : Mode sans interface graphique
- `cookies_only` : Utiliser uniquement les cookies (pas de login)

**Modes de scraping disponibles :**

| Mode | Description | Limite avis |
|------|-------------|-------------|
| `url` | URL simple (page produit) | ~10 avis |
| `url_auth` | URL + connexion Amazon | Illimité |
| `search` | Recherche multi-produits | Variable |
| `trustpilot` | Avis TrustPilot | Selon site |
| `yelp` | Avis Yelp | Selon business |

**Vérifier l'avancement :**
```bash
GET /tasks/{task_id}
```

**Attendre que le status soit `completed` avant de passer à l'étape 2.**

---

### Étape 2 : Analyse de sentiment

Une fois le scraping terminé, analyser les sentiments des avis.

**Pour une session spécifique :**
```bash
POST /analysis/sentiment
```
```json
{
  "scrape_task_id": "cf6e0af1-d2c4-41e9-8f4e-c8fbbe7500bc",
  "use_gpu": true
}
```

**Pour tous les avis non analysés :**
```json
{
  "use_gpu": true
}
```

**Paramètres :**
- `scrape_task_id` : ID de la session de scraping (optionnel, null = tous les avis)
- `use_gpu` : Utiliser le GPU si disponible (true recommandé)

---

### Étape 3 : Génération de réponses

Après l'analyse de sentiment, générer les réponses automatiques.

**Pour une session spécifique :**
```bash
POST /analysis/responses
```
```json
{
  "scrape_task_id": "cf6e0af1-d2c4-41e9-8f4e-c8fbbe7500bc",
  "use_gpu": true,
  "output_csv": true,
  "output_json": false
}
```

**Pour tous les avis analysés :**
```json
{
  "use_gpu": true,
  "output_csv": true,
  "output_json": false
}
```

**Paramètres :**
- `scrape_task_id` : ID de la session (optionnel)
- `use_gpu` : Utiliser le GPU
- `output_csv` : Exporter en CSV
- `output_json` : Exporter en JSON

**Suivi de la génération :**
```bash
GET /tasks/{analysis_task_id}
```

**Progression typique :**
```
50 avis sans réponse trouvés
Génération de 50 réponses...
Batch 1/5 (10 réponses)
10/50 réponses générées
...
50/50 réponses générées
Export des résultats...
CSV exporté : data/results/analysis/reviews_with_responses_cf6e0af1.csv
Génération terminée : 50 réponses
```

---

### Étape 4 : Récupération des résultats

**Via fichiers exportés :**

Les fichiers sont dans `data/results/analysis/` :
```
data/results/analysis/
├── reviews_with_responses_cf6e0af1-d2c4-41e9-8f4e.csv
└── reviews_with_responses_cf6e0af1-d2c4-41e9-8f4e.json
```

**Structure du CSV :**
```csv
id,session_task_id,produit_titre_complet,brand,Nom,Titre de l'avis,etoiles_valeur,Date_str,Avis,sentiment,score_sentiment,reponse_generee,platform
1,cf6e0af1-...,Ryzen 9 5900X,AMD,Droulez,Processeur au top,5.0,12 janvier 2024,Je suis passé d'un Ryzen...,positif,0.987,Nous vous remercions...,amazon
```

**Via base de données :**
```bash
sqlite3 data/avis_scraping.db
```
```sql
-- Voir les sessions
SELECT * FROM sessions_scraping ORDER BY date_extraction DESC;

-- Voir les avis avec sentiment et réponses
SELECT 
    id, 
    profil, 
    sentiment, 
    etoiles_valeur,
    substr(contenu, 1, 50) as extrait_avis,
    substr(reponse_generee, 1, 50) as extrait_reponse
FROM avis 
WHERE sentiment IS NOT NULL 
LIMIT 10;
```

---

## API Endpoints

### Scraping

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/scrape` | Lancer un scraping |
| GET | `/tasks` | Liste de toutes les tâches |

### Analyse

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/analysis/sentiment` | Analyser les sentiments |
| POST | `/analysis/responses` | Générer les réponses |

### Système

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/health` | État du système |

---

## Structure du projet
```
github_project_web_scrapp_amazon/
├── app/
│   ├── core/
│   │   ├── task_manager.py          # Gestion des tâches de scraping
│   │   ├── analysis_task_manager.py # Gestion des tâches d'analyse
│   │   ├── scraper_wrapper.py       # Wrapper scraping
│   │   ├── analyze_wrapper.py       # Wrapper analyse
│   │   └── review_pipeline.py       # Pipeline IA (sentiment + réponses)
│   ├── routes/
│   │   ├── scraping.py              # Routes scraping
│   │   ├── analysis.py              # Routes analyse
│   │   └── tasks.py                 # Routes monitoring
│   ├── scrapers/
│   │   ├── amazon_scraper.py        # Scraper Amazon
│   │   ├── trustpilot_scraper.py    # Scraper TrustPilot
│   │   └── yelp_scraper.py          # Scraper Yelp
│   ├── models/
│   │   └── schemas.py               # Schémas Pydantic
│   ├── database.py                  # Modèles SQLAlchemy
│   ├── crud.py                      # Opérations BDD
│   ├── config.py                    # Configuration
│   └── main.py                      # Point d'entrée FastAPI
├── data/
│   ├── avis_scraping.db             # Base SQLite (créée auto)
│   └── results/                     # Exports CSV/JSON
├── pyproject.toml                   # Dépendances UV
├── .gitignore                       # Fichiers ignorés par Git
└── README.md                        # Ce fichier
```

---

## Configuration

### Variables d'environnement

Créer un fichier `.env` à la racine (optionnel) :
```bash
# Chemins
RESULTS_DIR=./data/results
SELENIUM_PROFILE_DIR=./data/selenium_profiles

# Selenium
DEFAULT_WAIT_SECONDS=15

# Modèles IA (par défaut)
SENTIMENT_MODEL=nlptown/bert-base-multilingual-uncased-sentiment
RESPONSE_MODEL=mistralai/Mistral-7B-Instruct-v0.2
```

### Modes de scraping Amazon

**Mode URL simple** (10 avis max)
```json
{
  "mode": "url",
  "product_url": "https://www.amazon.fr/dp/B0XXXXXX"
}
```

**Mode URL authentifié** (100)
```json
{
  "mode": "url_auth",
  "product_url": "https://www.amazon.fr/dp/B0XXXXXX",
  "username": "email@amazon.fr",
  "password": "mot-de-passe"
}
```

**Mode recherche multi-produits**
```json
{
  "mode": "search",
  "query": "processeur gaming",
  "nb_products": 5,
  "limit_per_product": 10
}
```

---

## Base de données

### Structure

**3 tables principales :**

**sessions_scraping**
- `id` : ID auto-incrémenté
- `task_id` : ID unique de la tâche (UUID)
- `type_scraping` : Type de scraping
- `source` : Source (amazon, trustpilot, yelp)
- `nb_avis_extraits` : Nombre d'avis récupérés
- `statut` : État (running, completed, failed)
- `date_extraction` : Date du scraping

**produits**
- `id` : ID auto-incrémenté
- `session_id` : Lien vers session
- `titre` : Nom du produit
- `marque` : Marque
- `url` : URL du produit

**avis**
- `id` : ID auto-incrémenté
- `session_id` : Lien vers session
- `produit_id` : Lien vers produit
- `profil` : Nom de l'auteur
- `contenu` : Texte de l'avis
- `etoiles_valeur` : Note (0-5)
- `sentiment` : Sentiment analysé (positif/neutre/négatif)
- `score_sentiment` : Score de confiance (0-1)
- `reponse_generee` : Réponse automatique générée
- `statut` : État (scraped, analyzed, responded)

