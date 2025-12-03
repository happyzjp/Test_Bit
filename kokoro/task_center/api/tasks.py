from fastapi import APIRouter, Depends, HTTPException, Security, Request
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta, timezone

from kokoro.common.database import get_db
from kokoro.common.models.task import Task, TaskStatus, PublishStatus
from kokoro.common.auth.api_key import verify_api_key
from kokoro.task_center.services.task_dispatcher import TaskDispatcher
from kokoro.task_center.services.task_repository import TaskRepository
from kokoro.task_center.services.task_validator import TaskValidator, TaskValidationError
from kokoro.task_center.schemas.task import TaskCreate, TaskResponse, TaskListResponse
from kokoro.common.utils.logging import setup_logger
from kokoro.task_center.shared import miner_cache

router = APIRouter()
logger = setup_logger(__name__)
logger.info("init log test restart python 3")

@router.post("/publish", response_model=TaskResponse)
async def publish_task(
    task_data: TaskCreate,
    request: Request,
    api_key: str = Security(verify_api_key),  # API key verification happens here before function execution
    db: Session = Depends(get_db)
):
    # If we reach here, API key has been verified successfully
    logger.info(f"Task publish request received from authorized source (API key verified): {task_data.workflow_id}")
    
    # Validate task data - convert Pydantic models to dicts
    try:
        if hasattr(task_data, 'model_dump'):
            task_dict = task_data.model_dump()
        elif hasattr(task_data, 'dict'):
            task_dict = task_data.dict()
        else:
            task_dict = task_data
        
        # Convert workflow_spec to dict if it's a Pydantic model
        workflow_spec = task_dict.get('workflow_spec')
        if workflow_spec:
            if hasattr(workflow_spec, 'model_dump'):
                workflow_spec_dict = workflow_spec.model_dump()
            elif hasattr(workflow_spec, 'dict'):
                workflow_spec_dict = workflow_spec.dict()
            else:
                workflow_spec_dict = workflow_spec
            
            # Validate workflow spec
            is_valid, errors = TaskValidator.validate_workflow_spec(workflow_spec_dict)
            if not is_valid:
                error_message = "; ".join(errors)
                logger.warning(f"Task validation failed for {task_data.workflow_id}: {error_message}")
                raise HTTPException(status_code=400, detail=f"Task validation failed: {error_message}")
        
        # Validate complete task
        is_valid, errors = TaskValidator.validate_task_create(task_dict)
        if not is_valid:
            error_message = "; ".join(errors)
            logger.warning(f"Task validation failed for {task_data.workflow_id}: {error_message}")
            raise HTTPException(status_code=400, detail=f"Task validation failed: {error_message}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating task {task_data.workflow_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Task validation error: {str(e)}")
    
    dispatcher = TaskDispatcher(db, miner_cache)
    repository = TaskRepository(db)

    existing_task = repository.get_by_workflow_id(task_data.workflow_id)
    db.refresh(existing_task)
    if existing_task:
        if existing_task.publish_status == PublishStatus.PUBLISHED:
            raise HTTPException(status_code=400, detail="Task already published")

        now = datetime.now(timezone.utc)
        announcement_duration = task_data.announcement_duration
        execution_duration = task_data.execution_duration
        review_duration = task_data.review_duration
        reward_duration = getattr(task_data, "reward_duration", 0.0)

        announcement_start = now
        execution_start = announcement_start + timedelta(days=announcement_duration)
        review_start = execution_start + timedelta(days=execution_duration)
        reward_start = review_start + timedelta(days=review_duration)
        workflow_end = reward_start + timedelta(days=reward_duration)

        existing_task.workflow_type = task_data.workflow_type
        existing_task.workflow_spec = task_data.workflow_spec.dict()
        existing_task.status = TaskStatus.ANNOUNCEMENT
        existing_task.publish_status = PublishStatus.PUBLISHED
        existing_task.start_date = getattr(task_data, "start_date", existing_task.start_date)
        existing_task.end_date = getattr(task_data, "end_date", existing_task.end_date)
        existing_task.description = getattr(task_data, "description", existing_task.description)
        existing_task.hf_dataset_url = getattr(task_data, "hf_dataset_url", existing_task.hf_dataset_url)
        existing_task.pdf_file_url = getattr(task_data, "pdf_file_url", existing_task.pdf_file_url)
        existing_task.announcement_start = announcement_start
        existing_task.execution_start = execution_start
        existing_task.review_start = review_start
        existing_task.reward_start = reward_start
        existing_task.workflow_end = workflow_end

        db.commit()
        db.refresh(existing_task)
        task = existing_task

        try:
            await dispatcher._assign_task_to_miners(task)  # type: ignore[attr-defined]
        except Exception as e:
            logger.error(f"Failed to assign existing task {task.workflow_id} to miners: {e}", exc_info=True)
    else:
        task = dispatcher.create_task(task_data)

    selected_miners = dispatcher.select_miners_for_task(task_data.workflow_id)
    logger.info(f"Selected {len(selected_miners)} miners for task {task_data.workflow_id}")

    return TaskResponse.from_orm(task)


@router.get("/{workflow_id}", response_model=TaskResponse)
async def get_task(
    workflow_id: str,
    request: Request,
    api_key: str = Security(verify_api_key),
    db: Session = Depends(get_db)
):
    repository = TaskRepository(db)
    task = repository.get_by_workflow_id(workflow_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.from_orm(task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: TaskStatus = None,
    page: int = 1,
    page_size: int = 20,
    api_key: str = Security(verify_api_key),
    db: Session = Depends(get_db)
):
    repository = TaskRepository(db)
    tasks, total = repository.list_tasks(status=status, page=page, page_size=page_size)
    
    return TaskListResponse(
        workflows=[TaskResponse.from_orm(t) for t in tasks],
        pagination={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    )


@router.get("/pending")
async def get_pending_tasks(
    request: Request,
    api_key: str = Security(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Get pending tasks for validators to verify.
    Returns tasks with miner submissions that are pending verification.
    According to architecture doc section 6.4: GET /v1/tasks/pending
    """
    from kokoro.common.models.miner_submission import MinerSubmission
    from kokoro.common.models.audit_task import AuditTask
    
    # Get all tasks in EXECUTION or REVIEW status
    repository = TaskRepository(db)
    active_tasks = db.query(Task).filter(
        Task.status.in_([TaskStatus.EXECUTION, TaskStatus.REVIEW])
    ).all()
    
    pending_tasks = []
    for task in active_tasks:
        # Get miner submissions for this task
        submissions = db.query(MinerSubmission).filter(
            MinerSubmission.workflow_id == task.workflow_id,
            MinerSubmission.status == "pending_verification"
        ).all()
        
        for submission in submissions:
            # Check if audit tasks exist and are not all completed
            audit_tasks = db.query(AuditTask).filter(
                AuditTask.original_task_id == task.workflow_id,
                AuditTask.miner_hotkey == submission.miner_hotkey
            ).all()
            
            # If no audit tasks or some are not completed, task is pending
            if not audit_tasks or not all(t.is_completed for t in audit_tasks):
                pending_tasks.append({
                    "workflow_id": task.workflow_id,
                    "workflow_type": task.workflow_type,
                    "workflow_spec": task.workflow_spec,
                    "miner_hotkey": submission.miner_hotkey,
                    "lora_url": submission.model_url,
                    "submission_id": submission.id,
                    "submitted_at": submission.created_at.isoformat() if submission.created_at else None,
                    "task_status": task.status.value,
                    "audit_status": {
                        "total_audits": len(audit_tasks),
                        "completed_audits": sum(1 for t in audit_tasks if t.is_completed),
                        "pending_audits": sum(1 for t in audit_tasks if not t.is_completed)
                    }
                })
    
    return {
        "pending_tasks": pending_tasks,
        "total": len(pending_tasks)
    }

