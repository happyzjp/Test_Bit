from fastapi import APIRouter, Depends, Security, Request
from sqlalchemy.orm import Session
from kokoro.common.database import get_db
from kokoro.common.auth.api_key import verify_api_key
from kokoro.task_center.services.audit_task_creator import AuditTaskCreator
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


@router.post("/create")
async def create_audit_task(
    workflow_id: str,
    miner_hotkey: str,
    lora_url: str,
    request: Request,
    api_key: str = Security(verify_api_key),
    db: Session = Depends(get_db)
):
    creator = AuditTaskCreator(db)
    audit_task = creator.create_audit_task(workflow_id, miner_hotkey, lora_url)
    
    creator.auto_assign_audit_tasks(workflow_id)
    logger.info(f"Audit task created and auto-assigned: {audit_task.audit_task_id}")
    
    return {"audit_task_id": audit_task.audit_task_id, "status": "created"}

