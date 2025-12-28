from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.models.schemas import TaskStatus, TasksList
from app.core.task_manager import task_manager
import os

router = APIRouter(prefix="/tasks", tags=["Tâches"])

@router.get("", response_model=TasksList)
async def list_all_tasks():
    tasks = task_manager.get_all_tasks()
    return TasksList(total=len(tasks), tasks=tasks)

@router.get("/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    return TaskStatus(**task)

@router.delete("/{task_id}")
async def delete_task(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    if task["status"] == "running":
        raise HTTPException(status_code=400, detail="Tâche en cours")
    if task_manager.delete_task(task_id):
        return {"message": f"Tâche {task_id} supprimée"}
    raise HTTPException(status_code=500, detail="Erreur")

@router.get("/{task_id}/download")
async def download_results(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Tâche non terminée")
    if not task["result_file"] or not os.path.exists(task["result_file"]):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(
        path=task["result_file"],
        filename=f"amazon_reviews_{task_id}.json",
        media_type="application/json"
    )