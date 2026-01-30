from fastapi import APIRouter, BackgroundTasks
from app.models.schemas import ScrapeRequest, ScrapeResponse, ScrapeMode
from app.core.task_manager import task_manager
from app.core.scraper_wrapper import execute_scraping_task

router = APIRouter(prefix="/scrape", tags=["Webscraping des avis clients"])


@router.post("", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Lancer un scraping (modes disponibles)

    ==========================
     Mode SEARCH (Amazon)
    ==========================
    Scrape plusieurs produits via une recherche Amazon.

    **Exemple :**
    ```json
    {
      "mode": "search",
      "query": "écran pc",
      "nb_products": 10,
      "france_only": true,
      "limit_per_product": 5,
      "headless": true
    }
    ```

    ==========================
     Mode URL (Amazon)
    ==========================
    Scrape un seul produit via son URL Amazon (avis visibles sur la page produit).

    **Exemple :**
    ```json
    {
      "mode": "url",
      "product_url": "https://www.amazon.fr/dp/B0F1FSGNLT",
      "france_only": true,
      "limit_per_product": 50,
      "headless": true
    }
    ```

    ==========================
     Mode URL_AUTH (Amazon authentifié)
    ==========================
    Scrape un seul produit via son URL Amazon, **en étant connecté** (accès à la page complète des avis).

    Fonctionnement:
    - Le scraper tente d'abord de charger les cookies depuis: `app/results/amazon_session_cookies.pkl`
    - Si les cookies sont valides -> connexion automatique (aucune saisie)
    - Si les cookies sont invalides:
      - si `cookies_only=true` -> échec
      - si `cookies_only=false` -> login via `username/password`, puis sauvegarde des cookies

    **Exemple (cookies + fallback login) :**
    ```json
    {
      "mode": "url_auth",
      "product_url": "https://www.amazon.fr/dp/B0F1FSGNLT",
      "cookies_only": false,
      "username": "email@example.com",
      "password": "motdepasse",
      "france_only": false,
      "limit_per_product": 100,
      "headless": true
    }
    ```

    **Exemple (cookies only, aucune saisie) :**
    ```json
    {
      "mode": "url_auth",
      "product_url": "https://www.amazon.fr/dp/B0F1FSGNLT",
      "cookies_only": true,
      "france_only": false,
      "limit_per_product": 200,
      "headless": true
    }
    ```

    ==========================
     Mode TRUSTPILOT
    ==========================
    Scrape les avis Trustpilot d'un domaine (ex: 'carhartt-wip.com').

    Sortie JSON: **même structure que Amazon** (liste `avis[]` avec `profil`, `titre_review`, `date`, `contenu`, etc).

    **Exemple :**
    ```json
    {
      "mode": "trustpilot",
      "trustpilot_domain": "carhartt-wip.com",
      "trustpilot_lang": "fr",
      "max_pages": 5,
      "limit_per_product": 200
    }
    ```

    ==========================
     Mode YELP
    ==========================
    Scrape les avis Yelp d'une page business (Selenium).

    Sortie JSON: **même structure que Amazon** (liste `avis[]` avec `profil`, `date`, `contenu`, etc).

    **Exemple :**
    ```json
    {
      "mode": "yelp",
      "yelp_business_url": "https://www.yelp.fr/biz/le-petit-cler-paris",
      "max_pages": 2,
      "limit_per_product": 20,
      "headless": false
    }
    ```
    """

    # Créer la tâche
    task_id = task_manager.create_task(request)

    # Lancer en arrière-plan
    background_tasks.add_task(execute_scraping_task, task_id, request.model_dump())

    # Message personnalisé selon le mode
    if request.mode == ScrapeMode.URL:
        message = "Scraping lancé (Amazon - mode URL) pour le produit"
    elif request.mode == ScrapeMode.URL_AUTH:
        message = "Scraping lancé (Amazon - mode URL_AUTH) pour le produit"
    elif request.mode == ScrapeMode.TRUSTPILOT:
        message = "Scraping lancé (Trustpilot)"
    elif request.mode == ScrapeMode.YELP:
        message = "Scraping lancé (Yelp)"
    else:
        message = f"Scraping lancé (Amazon - mode recherche) pour '{request.query}'"

    return ScrapeResponse(
        task_id=task_id,
        status="pending",
        message=message,
        mode=request.mode.value
    )
