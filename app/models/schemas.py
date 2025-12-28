from pydantic import BaseModel, Field
from typing import Optional, Dict

class ScrapeRequest(BaseModel):
    query: str = Field(..., min_length=1)
    nb_products: int = Field(default=10, ge=1, le=100)
    france_only: bool = Field(default=True)
    limit_per_product: Optional[int] = Field(default=None, ge=1)
    headless: bool = Field(default=True)

class ScrapeResponse(BaseModel):
    task_id: str
    status: str
    message: str

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: Optional[str] = None
    result_file: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

class TasksList(BaseModel):
    total: int
    tasks: Dict[str, TaskStatus]

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    active_tasks: int
    total_tasks: int