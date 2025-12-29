# app/api/routes/scraping.py

from fastapi import APIRouter, BackgroundTasks
from app.models.schemas import ScrapeRequest, ScrapeResponse, ScrapeMode
from app.core.task_manager import task_manager
from app.core.scraper_wrapper import execute_scraping_task

router = APIRouter(prefix="/scrape", tags=["Scraping"])


@router.post("", response_model=ScrapeResponse)
async def scrape_amazon(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Lancer un scraping Amazon (2 modes disponibles)
    
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
    Scrape un seul produit via son URL Amazon
    
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
    """
    
    # Créer la tâche
    task_id = task_manager.create_task(request)
    
    # Lancer en arrière-plan
    background_tasks.add_task(execute_scraping_task, task_id, request.dict())
    
    # Message personnalisé selon le mode
    if request.mode == ScrapeMode.URL:
        message = f"Scraping lancé (mode URL) pour le produit"
    else:
        message = f"Scraping lancé (mode recherche) pour '{request.query}'"
    
    return ScrapeResponse(
        task_id=task_id,
        status="pending",
        message=message,
        mode=request.mode.value
    )