from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict
import uvicorn
import json
import os
from datetime import datetime
import uuid

# Import du scraper (fichier scraper.py)
from scraper import AmazonReviewScraper


# ========== CONFIGURATION ==========

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# ========== MODELS PYDANTIC ==========

class ScrapeRequest(BaseModel):
    """Modèle de requête pour lancer un scraping"""
    query: str = Field(..., description="Terme de recherche Amazon (ex: 'écran pc')", min_length=1)
    nb_products: int = Field(default=10, ge=1, le=100, description="Nombre de produits à scraper")
    france_only: bool = Field(default=True, description="Filtrer uniquement les avis français")
    limit_per_product: Optional[int] = Field(default=None, ge=1, description="Limite d'avis par produit")
    headless: bool = Field(default=True, description="Mode sans interface graphique")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "écran pc",
                "nb_products": 10,
                "france_only": True,
                "limit_per_product": 5,
                "headless": True
            }
        }


class ScrapeResponse(BaseModel):
    """Réponse lors du lancement d'un scraping"""
    task_id: str
    status: str
    message: str


class TaskStatus(BaseModel):
    """Statut d'une tâche de scraping"""
    task_id: str
    status: str  # "pending", "running", "completed", "failed"
    progress: Optional[str] = None
    result_file: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TasksList(BaseModel):
    """Liste de toutes les tâches"""
    total: int
    tasks: Dict[str, TaskStatus]


# ========== STOCKAGE DES TÂCHES ==========

tasks_status: Dict[str, dict] = {}


# ========== FONCTIONS DE SCRAPING ==========

def run_scraping_task(task_id: str, request: ScrapeRequest):
    """
    Fonction exécutée en arrière-plan pour chaque tâche de scraping
    
    Args:
        task_id: Identifiant unique de la tâche
        request: Paramètres du scraping
    """
    try:
        # Mise à jour du statut
        tasks_status[task_id]["status"] = "running"
        tasks_status[task_id]["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Créer le scraper
        scraper = AmazonReviewScraper(
            profile_dir="~/.selenium_profiles/amazon",
            headless=request.headless,
            wait_seconds=15
        )
        
        # Définir le callback de progression
        def update_progress(message: str):
            tasks_status[task_id]["progress"] = message
        
        scraper.set_progress_callback(update_progress)
        
        # Lancer le scraping
        result = scraper.scrape_multiple_products(
            query=request.query,
            nb_products=request.nb_products,
            france_only=request.france_only,
            limit_per_product=request.limit_per_product
        )
        
        # Sauvegarder le résultat
        output_file = os.path.join(RESULTS_DIR, f"amazon_reviews_{task_id}.json")
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Mise à jour finale
        tasks_status[task_id]["status"] = "completed"
        tasks_status[task_id]["result_file"] = output_file
        tasks_status[task_id]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tasks_status[task_id]["progress"] = (
            f"Terminé: {result['nb_produits_scrapes']} produits, "
            f"{result['total_avis_extraits']} avis extraits"
        )
        
    except Exception as e:
        # En cas d'erreur
        tasks_status[task_id]["status"] = "failed"
        tasks_status[task_id]["error"] = str(e)
        tasks_status[task_id]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tasks_status[task_id]["progress"] = f"Erreur: {str(e)[:100]}"


# ========== FASTAPI APPLICATION ==========

app = FastAPI(
    title="Amazon Review Scraper API",
    description=(
        "API pour scraper les avis de produits Amazon France.\n\n"
        "**Fonctionnalités:**\n"
        "- Scraping asynchrone avec suivi en temps réel\n"
        "- Gestion multi-tâches\n"
        "- Téléchargement des résultats en JSON\n"
        "- Filtrage des avis français\n"
        "- Pagination automatique"
    ),
    version="2.0.0",
    contact={
        "name": "Support",
        "email": "support@example.com"
    }
)

# CORS (si besoin d'accès depuis un frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== ENDPOINTS ==========

@app.get("/", tags=["Info"])
async def root():
    """
    🏠 Page d'accueil de l'API
    
    Affiche les endpoints disponibles et des informations générales.
    """
    return {
        "name": "Amazon Review Scraper API",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": {
            "POST /scrape": "Lancer un nouveau scraping",
            "GET /tasks": "Lister toutes les tâches",
            "GET /status/{task_id}": "Vérifier le statut d'une tâche",
            "GET /download/{task_id}": "Télécharger les résultats",
            "DELETE /task/{task_id}": "Supprimer une tâche",
            "GET /docs": "Documentation Swagger interactive",
            "GET /health": "État de santé de l'API"
        },
        "documentation": "/docs"
    }


@app.get("/health", tags=["Info"])
async def health_check():
    """
    Vérifier l'état de santé de l'API
    
    Retourne le statut opérationnel et le nombre de tâches actives.
    """
    running_tasks = sum(1 for t in tasks_status.values() if t["status"] == "running")
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_tasks": running_tasks,
        "total_tasks": len(tasks_status)
    }


@app.post("/scrape", response_model=ScrapeResponse, tags=["Scraping"])
async def scrape_amazon(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Lancer un scraping Amazon en arrière-plan
    
    **Paramètres:**
    - **query**: Terme de recherche (ex: "écran pc", "souris gaming")
    - **nb_products**: Nombre de produits à scraper (1-100)
    - **france_only**: `true` = seulement avis français, `false` = tous les avis
    - **limit_per_product**: Limite d'avis par produit (optionnel)
    - **headless**: `true` = mode sans interface, `false` = voir le navigateur
    
    **Retour:**
    - Un `task_id` unique pour suivre la progression via `/status/{task_id}`
    
    **Exemple:**
    ```json
    {
      "query": "écran pc",
      "nb_products": 10,
      "france_only": true,
      "limit_per_product": 5,
      "headless": true
    }
    ```
    """
    # Générer un ID unique
    task_id = str(uuid.uuid4())
    
    # Initialiser le statut
    tasks_status[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": "En attente de démarrage...",
        "result_file": None,
        "error": None,
        "started_at": None,
        "completed_at": None,
        "request": request.dict()
    }
    
    # Lancer la tâche en arrière-plan
    background_tasks.add_task(run_scraping_task, task_id, request)
    
    return ScrapeResponse(
        task_id=task_id,
        status="pending",
        message=f"Scraping lancé pour '{request.query}' - Utilisez /status/{task_id} pour suivre"
    )


@app.get("/tasks", response_model=TasksList, tags=["Tâches"])
async def list_all_tasks():
    """
    Lister toutes les tâches de scraping
    
    Retourne la liste complète de toutes les tâches (en cours, terminées, échouées).
    """
    return TasksList(
        total=len(tasks_status),
        tasks=tasks_status
    )


@app.get("/status/{task_id}", response_model=TaskStatus, tags=["Tâches"])
async def get_task_status(task_id: str):
    """
    🔍 Récupérer le statut d'une tâche
    
    **Statuts possibles:**
    - `pending`: En attente de démarrage
    - `running`: Scraping en cours
    - `completed`: Terminé avec succès
    - `failed`: Échec (voir le champ `error`)
    
    Le champ `progress` est mis à jour en temps réel pendant le scraping.
    """
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    
    return TaskStatus(**tasks_status[task_id])


@app.get("/download/{task_id}", tags=["Résultats"])
async def download_results(task_id: str):
    """
    Télécharger les résultats d'une tâche
    
    Télécharge le fichier JSON contenant tous les avis scrapés.
    
    **Prérequis:** La tâche doit avoir le statut `completed`.
    """
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    
    task = tasks_status[task_id]
    
    if task["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Tâche non terminée (statut actuel: {task['status']})"
        )
    
    if not task["result_file"] or not os.path.exists(task["result_file"]):
        raise HTTPException(status_code=404, detail="Fichier de résultats introuvable")
    
    return FileResponse(
        path=task["result_file"],
        filename=f"amazon_reviews_{task_id}.json",
        media_type="application/json"
    )


@app.delete("/task/{task_id}", tags=["Tâches"])
async def delete_task(task_id: str):
    """
    Supprimer une tâche et ses résultats
    
    Supprime la tâche de la mémoire et le fichier de résultats du disque.
    
    **Note:** Les tâches en cours (`running`) ne peuvent pas être supprimées.
    """
    if task_id not in tasks_status:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    
    task = tasks_status[task_id]
    
    if task["status"] == "running":
        raise HTTPException(
            status_code=400,
            detail="Impossible de supprimer une tâche en cours d'exécution"
        )
    
    # Supprimer le fichier de résultats
    if task["result_file"] and os.path.exists(task["result_file"]):
        try:
            os.remove(task["result_file"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")
    
    # Supprimer de la mémoire
    del tasks_status[task_id]
    
    return {"message": f"Tâche {task_id} supprimée avec succès"}

if __name__ == "__main__":
 
    print(f"URL de l'API: http://localhost:8000")
    print(f"Documentation: http://localhost:8000/docs")
    print("="*70 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )