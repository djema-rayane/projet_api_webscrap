from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.models.schemas import TaskStatus, TasksList
from app.core.task_manager import task_manager
import os

router = APIRouter(prefix="/tasks", tags=["Historique des tâches"])

@router.get("", response_model=TasksList)
async def list_all_tasks():
    tasks = task_manager.get_all_tasks()
    return TasksList(total=len(tasks), tasks=tasks)




