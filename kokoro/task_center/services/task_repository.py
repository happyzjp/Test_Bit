from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import Optional, Tuple, List
from kokoro.common.models.task import Task, TaskStatus
from kokoro.common.models.miner_submission import MinerSubmission
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class TaskRepository:
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_by_workflow_id(self, workflow_id: str) -> Optional[Task]:
        return self.db.query(Task).filter(Task.workflow_id == workflow_id).first()
    
    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Task], int]:
        query = self.db.query(Task)
        
        if status:
            query = query.filter(Task.status == status)
        
        total = query.count()
        
        tasks = query.offset((page - 1) * page_size).limit(page_size).all()
        
        return tasks, total
    
    def update_status(self, workflow_id: str, status: TaskStatus):
        task = self.get_by_workflow_id(workflow_id)
        if task:
            task.status = status
            self.db.commit()
    
    def get_submissions_by_workflow(self, workflow_id: str) -> List[MinerSubmission]:
        return self.db.query(MinerSubmission).filter(
            MinerSubmission.workflow_id == workflow_id
        ).all()
    
    def get_submission_by_id(self, submission_id: str) -> Optional[MinerSubmission]:
        return self.db.query(MinerSubmission).filter(
            MinerSubmission.id == submission_id
        ).first()

