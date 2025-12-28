from fastapi import APIRouter, BackgroundTasks
from app.models.schemas import ScrapeRequest, ScrapeResponse
from app.core.task_manager import task_manager
from app.core.scraper_wrapper import execute_scraping_task

router = APIRouter(prefix="/scrape", tags=["Scraping"])

@router.post("", response_model=ScrapeResponse)
async def scrape_amazon(request: ScrapeRequest, background_tasks: BackgroundTasks):
    task_id = task_manager.create_task(request)
    background_tasks.add_task(execute_scraping_task, task_id, request.dict())
    return ScrapeResponse(
        task_id=task_id,
        status="pending",
        message=f"Scraping lancé pour '{request.query}'"
    )