# app/api/routes/scraping.py

from fastapi import APIRouter, BackgroundTasks
from app.models.schemas import ScrapeRequest, ScrapeResponse, ScrapeMode
from app.core.task_manager import task_manager
from app.core.scraper_wrapper import execute_scraping_task

router = APIRouter(prefix="/scrape", tags=["Scraping"])


@router.post("", response_model=ScrapeResponse)
async def scrape_amazon(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Lancer un scraping Amazon (modes disponibles)

    ## Mode SEARCH (par défaut)
    Scrape plusieurs produits via une recherche Amazon

    **Exemple:**
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

    ## Mode URL
    Scrape un seul produit via son URL Amazon (avis visibles sur la page produit)

    **Exemple:**
    ```json
    {
      "mode": "url",
      "product_url": "https://www.amazon.fr/dp/B0F1FSGNLT",
      "france_only": true,
      "limit_per_product": 50,
      "headless": true
    }
    ```

    ## Mode URL_AUTH (scraping authentifié)
    Scrape un seul produit via son URL Amazon, **en étant connecté** (pour accéder à davantage d'avis
    ou à la page complète des commentaires).

    - Fournir `username` + `password` dans le body.
    Une fois connecté, vos cookies de sessions seront enregistrés dans un sous dossier result, et le scrapping se connectera directement via les cookies
    **Exemple:**
    ```json
  {
    "mode": "url_auth",
    "product_url": "https://www.amazon.fr/dp/B0F1FSGNLT",
    "cookies_only": false,
    "username": "email@example.com",
    "password": "motdepasse",
    "france_only": false,
    "limit_per_product": 2,
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
        message = "Scraping lancé (mode URL) pour le produit"
        
    else:
        message = f"Scraping lancé (mode recherche) pour '{request.query}'"

    return ScrapeResponse(
        task_id=task_id,
        status="pending",
        message=message,
        mode=request.mode.value
    )
