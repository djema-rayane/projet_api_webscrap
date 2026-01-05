import os
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.config import settings
from app.core.analysis_task_manager import analysis_task_manager
from app.core.analyze_wrapper import execute_analysis_task
from app.core.review_selectors import load_review_from_scrape_json

from app.models.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisTaskStatus,
    ReplyOneRequest,
    ReplyOneResponse,
)

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("", response_model=AnalysisResponse)
async def launch_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """
    Répondre à TOUS les avis (pipeline complet) -> export CSV (tâche background)
    """
    analysis_task_id = analysis_task_manager.create_task(request.scrape_task_id)

    background_tasks.add_task(
        execute_analysis_task,
        analysis_task_id,
        request.scrape_task_id,
        request.use_gpu,
        request.output_csv,
        request.output_json,
    )

    return AnalysisResponse(
        analysis_task_id=analysis_task_id,
        status="pending",
        message=f"Analyse lancée pour scrape_task_id={request.scrape_task_id}",
    )


@router.get("/{analysis_task_id}", response_model=AnalysisTaskStatus)
async def get_analysis_status(analysis_task_id: str):
    """
    Récupérer le statut et le fichier résultat de la tâche d'analyse
    """
    task = analysis_task_manager.get_task(analysis_task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche d'analyse introuvable")
    return task


@router.post("/reply-one", response_model=ReplyOneResponse)
async def reply_one(request: ReplyOneRequest):
    """
    Répondre à UN seul avis (réponse immédiate dans Swagger)
    """
    input_json = os.path.join(settings.results_dir, f"amazon_reviews_{request.scrape_task_id}.json")
    if not os.path.exists(input_json):
        raise HTTPException(status_code=404, detail="Fichier JSON de scraping introuvable")

    try:
        payload = load_review_from_scrape_json(
            json_path=input_json,
            product_index=request.product_index,
            review_numero=request.review_numero,
        )

        from app.core.review_pipeline import generate_reply_for_single_review

        result = generate_reply_for_single_review(
            product_title=payload["product_title"],
            brand=payload["brand"],
            avis=payload["avis"],
            use_gpu=request.use_gpu,
        )

        return ReplyOneResponse(
            scrape_task_id=request.scrape_task_id,
            product_index=request.product_index,
            review_numero=request.review_numero,
            sentiment=result["sentiment"],
            reply=result["reply"],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/warmup")
async def warmup_models(use_gpu: bool = True):
    """
    Pré-charger les modèles dans le cache (utile avant d'appeler reply-one).
    """
    from app.core.review_pipeline import get_cached_pipeline

    get_cached_pipeline(use_gpu=use_gpu)
    return {"status": "ok", "message": "Modèles chargés en cache"}
