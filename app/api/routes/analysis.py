from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.crud import get_session_by_task_id
from app.core.analysis_task_manager import analysis_task_manager
from app.core.analyze_wrapper import execute_sentiment_analysis_task, execute_response_generation_task

router = APIRouter(prefix="/analysis", tags=["Analyse et Génération"])


# ============================================================================
# SCHÉMAS
# ============================================================================

class SentimentAnalysisRequest(BaseModel):
    """Requête pour l'analyse de sentiment uniquement."""
    scrape_task_id: Optional[str] = Field(
        default=None,
        description="ID de la tâche de scraping (optionnel : None = tous les avis)"
    )
    use_gpu: bool = Field(default=True, description="Utiliser GPU si disponible")


class ResponseGenerationRequest(BaseModel):
    """Requête pour la génération de réponses uniquement."""
    scrape_task_id: Optional[str] = Field(
        default=None,
        description="ID de la tâche de scraping (optionnel : None = tous les avis)"
    )
    use_gpu: bool = Field(default=True, description="Utiliser GPU si disponible")
    output_csv: bool = Field(default=False, description="Export CSV optionnel")
    output_json: bool = Field(default=False, description="Export JSON optionnel")


class AnalysisResponse(BaseModel):
    """Réponse après lancement d'une tâche."""
    analysis_task_id: str
    status: str
    message: str
    target: str


# ============================================================================
# ROUTE 1 : ANALYSE DE SENTIMENT UNIQUEMENT
# ============================================================================

@router.post("/sentiment", response_model=AnalysisResponse)
async def analyze_sentiment(
    request: SentimentAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Analyser les sentiments des avis NON ANALYSÉS.
    
    Cette route remplit UNIQUEMENT la colonne `sentiment` dans la BDD.
    Elle ne génère PAS de réponses.
    
    **Modes :**
    
    1. **Tous les avis** (scrape_task_id = null) :
```json
       {
         "use_gpu": true
       }
```
    
    2. **Session spécifique** (scrape_task_id fourni) :
```json
       {
         "scrape_task_id": "cf6e0af1-d2c4-41e9-8f4e-c8fbbe7500bc",
         "use_gpu": true
       }
```
    
    **Workflow :**
    1. Récupère les avis avec `sentiment=NULL`
    2. Analyse le sentiment avec le modèle
    3. Met à jour `sentiment` et `score_sentiment` dans la BDD
    4. Ne touche PAS à `reponse_generee`
    """
    
    print(f"DEBUG: Analyse sentiment - scrape_task_id={request.scrape_task_id}")
    
    # Validation
    if request.scrape_task_id:
        session = get_session_by_task_id(db, request.scrape_task_id)
        print(f"DEBUG: Session trouvée = {session is not None}")
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session de scraping '{request.scrape_task_id}' introuvable"
            )
        
        target = f"session:{request.scrape_task_id}"
        message = f"Analyse de sentiment lancée pour la session '{request.scrape_task_id}'"
    else:
        target = "all"
        message = "Analyse de sentiment lancée pour tous les avis non analysés"
    
    # Créer un task_id
    analysis_task_id = analysis_task_manager.create_task(f"sentiment_{target}")
    print(f"DEBUG: analysis_task_id créé = {analysis_task_id}")
    
    # Lancer en arrière-plan
    print("DEBUG: Ajout de la tâche sentiment en background...")
    background_tasks.add_task(
        execute_sentiment_analysis_task,
        analysis_task_id,
        request.scrape_task_id,
        request.use_gpu,
    )
    print("DEBUG: Tâche ajoutée")
    
    return AnalysisResponse(
        analysis_task_id=analysis_task_id,
        status="pending",
        message=message,
        target=target,
    )


# ============================================================================
# ROUTE 2 : GÉNÉRATION DE RÉPONSES UNIQUEMENT
# ============================================================================

@router.post("/responses", response_model=AnalysisResponse)
async def generate_responses(
    request: ResponseGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Générer les réponses pour les avis ANALYSÉS sans réponse.
    
    Cette route remplit UNIQUEMENT la colonne `reponse_generee` dans la BDD.
    Elle requiert que les avis aient déjà un `sentiment` (via /sentiment).
    
    **Modes :**
    
    1. **Tous les avis** (scrape_task_id = null) :
```json
       {
         "use_gpu": true,
         "output_csv": true,
         "output_json": false
       }
```
    
    2. **Session spécifique** (scrape_task_id fourni) :
```json
       {
         "scrape_task_id": "cf6e0af1-d2c4-41e9-8f4e-c8fbbe7500bc",
         "use_gpu": true,
         "output_csv": true,
         "output_json": false
       }
```
    
    **Workflow :**
    1. Récupère les avis avec `sentiment != NULL` ET `reponse_generee = NULL`
    2. Génère les réponses avec le modèle
    3. Met à jour `reponse_generee` dans la BDD
    4. (Optionnel) Exporte en CSV/JSON
    """
    
    print(f"DEBUG: Génération réponses - scrape_task_id={request.scrape_task_id}")
    
    # Validation
    if request.scrape_task_id:
        session = get_session_by_task_id(db, request.scrape_task_id)
        print(f"DEBUG: Session trouvée = {session is not None}")
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session de scraping '{request.scrape_task_id}' introuvable"
            )
        
        target = f"session:{request.scrape_task_id}"
        message = f"Génération de réponses lancée pour la session '{request.scrape_task_id}'"
    else:
        target = "all"
        message = "Génération de réponses lancée pour tous les avis analysés"
    
    # Créer un task_id
    analysis_task_id = analysis_task_manager.create_task(f"responses_{target}")
    print(f"DEBUG: analysis_task_id créé = {analysis_task_id}")
    
    # Lancer en arrière-plan
    print("DEBUG: Ajout de la tâche responses en background...")
    background_tasks.add_task(
        execute_response_generation_task,
        analysis_task_id,
        request.scrape_task_id,
        request.use_gpu,
        request.output_csv,
        request.output_json,
    )
    print("DEBUG: Tâche ajoutée")
    
    return AnalysisResponse(
        analysis_task_id=analysis_task_id,
        status="pending",
        message=message,
        target=target,
    )