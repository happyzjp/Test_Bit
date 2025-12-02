from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from kokoro.common.database import get_db
from kokoro.task_center.services.audit_task_creator import AuditTaskCreator
from kokoro.task_center.schemas.audit import AuditTaskResponse, AuditTaskListResponse
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


@router.get("/pending", response_model=AuditTaskListResponse)
async def get_pending_audit_tasks(
    validator_key: str,
    db: Session = Depends(get_db)
):
    creator = AuditTaskCreator(db)
    tasks = creator.get_pending_tasks_for_validator(validator_key)
    
    return AuditTaskListResponse(
        tasks=[AuditTaskResponse.from_orm(t) for t in tasks]
    )


@router.post("/receive")
async def receive_audit_task(
    audit_task_id: str,
    validator_key: str,
    db: Session = Depends(get_db)
):
    creator = AuditTaskCreator(db)
    task = creator.assign_audit_task_to_validator(audit_task_id, validator_key)
    
    if not task:
        raise HTTPException(status_code=404, detail="Audit task not found")
    
    return AuditTaskResponse.from_orm(task)

