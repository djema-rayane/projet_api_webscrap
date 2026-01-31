from typing import Dict
from datetime import datetime
import uuid
import os

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, dict] = {}
    
    def create_task(self, request) -> str:
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": "En attente...",
            "result_file": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
            "request": request.dict()
        }
        return task_id
    
    def get_task(self, task_id: str) -> dict | None:
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> dict | None :
        return self.tasks
    
    def update_status(self, task_id: str, status: str):
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = status
            if status == "running":
                self.tasks[task_id]["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif status in ["completed", "failed"]:
                self.tasks[task_id]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def update_progress(self, task_id: str, message: str):
        if task_id in self.tasks:
            self.tasks[task_id]["progress"] = message
    
    def set_result(self, task_id: str, result_file: str, summary: str):
        if task_id in self.tasks:
            self.tasks[task_id]["result_file"] = result_file
            self.tasks[task_id]["progress"] = summary
    
    def set_error(self, task_id: str, error: str):
        if task_id in self.tasks:
            self.tasks[task_id]["error"] = error
            self.tasks[task_id]["progress"] = f"Erreur: {error[:100]}"
    
    def delete_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task["result_file"] and os.path.exists(task["result_file"]):  
                os.remove(task["result_file"])
            del self.tasks[task_id]
            return True
        return False
    
    def count_running_tasks(self) -> int:
        return sum(1 for t in self.tasks.values() if t["status"] == "running")

task_manager = TaskManager()