import uuid
from datetime import datetime
from typing import Dict, Optional


class AnalysisTaskManager:
    def __init__(self):
        self.tasks: Dict[str, dict] = {}

    def create_task(self, source_scrape_task_id: str) -> str:
        task_id = uuid.uuid4().hex[:12]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.tasks[task_id] = {
            "task_id": task_id,
            "source_scrape_task_id": source_scrape_task_id,
            "status": "pending",
            "progress": None,
            "result_file": None,
            "error": None,
            "started_at": now,
            "completed_at": None,
        }
        return task_id

    def update_status(self, task_id: str, status: str):
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = status
            if status in ("completed", "failed"):
                self.tasks[task_id]["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def update_progress(self, task_id: str, progress: str):
        if task_id in self.tasks:
            self.tasks[task_id]["progress"] = progress

    def set_result(self, task_id: str, result_file: str):
        if task_id in self.tasks:
            self.tasks[task_id]["result_file"] = result_file

    def set_error(self, task_id: str, error: str):
        if task_id in self.tasks:
            self.tasks[task_id]["error"] = error

    def get_task(self, task_id: str) -> Optional[dict]:
        return self.tasks.get(task_id)

    def list_tasks(self) -> Dict[str, dict]:
        return self.tasks


analysis_task_manager = AnalysisTaskManager()
