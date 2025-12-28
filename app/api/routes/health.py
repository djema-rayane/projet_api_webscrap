from fastapi import APIRouter
from app.models.schemas import HealthResponse
from app.core.task_manager import task_manager
from app.config import settings
from datetime import datetime

router = APIRouter(tags=["Info"])

@router.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "operational",
        "documentation": "/docs"
    }

@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        active_tasks=task_manager.count_running_tasks(),
        total_tasks=len(task_manager.get_all_tasks())
    )