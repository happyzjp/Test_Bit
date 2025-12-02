from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from kokoro.website_admin.schemas.task import (
    TaskPublishRequest, TaskPublishResponse, TaskQueryRequest, TaskListResponse, TaskInfo
)
from kokoro.common.utils.logging import setup_logger
from kokoro.common.config.yaml_config import YamlConfig
from kokoro.common.database import get_db
from kokoro.common.models.task import Task, TaskStatus, PublishStatus
from kokoro.common.models.workflow_type import WorkflowType
import httpx
import os
from typing import Optional
from datetime import datetime

router = APIRouter()
logger = setup_logger(__name__)

config_path = os.getenv("WEBSITE_ADMIN_CONFIG", "config.yml")
yaml_config = None
if os.path.exists(config_path):
    yaml_config = YamlConfig(config_path)

task_center_url = yaml_config.get_task_center_url() if yaml_config else "http://localhost:8000"
api_key = yaml_config.get('api.key') if yaml_config else None

logger.info(f"Task Center URL configured: {task_center_url}")


@router.post("/publish", response_model=TaskPublishResponse)
async def publish_task(request: TaskPublishRequest, db: Session = Depends(get_db)):
    try:
        # Check if task already exists
        existing_task = db.query(Task).filter(Task.workflow_id == request.workflow_id).first()
        
        # Convert workflow_spec to dict
        workflow_spec_dict = request.workflow_spec.model_dump() if hasattr(request.workflow_spec, 'model_dump') else request.workflow_spec.dict()
        
        # Convert workflow_type string to enum
        try:
            workflow_type_enum = WorkflowType(request.workflow_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid workflow_type: {request.workflow_type}")
        
        # Determine publish_status
        publish_status = PublishStatus.DRAFT if (request.publish_status or "draft").lower() == "draft" else PublishStatus.PUBLISHED
        
        if existing_task:
            # Update existing task
            existing_task.task_id = request.task_id or existing_task.task_id
            existing_task.workflow_type = workflow_type_enum
            existing_task.workflow_spec = workflow_spec_dict
            existing_task.publish_status = publish_status
            existing_task.start_date = request.start_date
            existing_task.end_date = request.end_date
            existing_task.description = request.description
            existing_task.hf_dataset_url = request.hf_dataset_url
            existing_task.pdf_file_url = request.pdf_file_url
            
            # If publishing (not draft), update status and call task center
            if publish_status == PublishStatus.PUBLISHED:
                existing_task.status = TaskStatus.ANNOUNCEMENT
                db.commit()
                db.refresh(existing_task)
                # Call task center API after saving to database
                try:
                    await _call_task_center_api(request)
                except HTTPException:
                    # If task center call fails, rollback status to PENDING
                    existing_task.status = TaskStatus.PENDING
                    existing_task.publish_status = PublishStatus.DRAFT
                    db.commit()
                    raise
            else:
                # Draft: keep status as PENDING
                existing_task.status = TaskStatus.PENDING
                db.commit()
                db.refresh(existing_task)
            
            task = existing_task
        else:
            # Create new task
            task = Task(
                task_id=request.task_id,
                workflow_id=request.workflow_id,
                workflow_type=workflow_type_enum,
                workflow_spec=workflow_spec_dict,
                status=TaskStatus.PENDING if publish_status == PublishStatus.DRAFT else TaskStatus.ANNOUNCEMENT,
                publish_status=publish_status,
                start_date=request.start_date,
                end_date=request.end_date,
                description=request.description,
                hf_dataset_url=request.hf_dataset_url,
                pdf_file_url=request.pdf_file_url
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            
            # If publishing (not draft), call task center API after saving to database
            if publish_status == PublishStatus.PUBLISHED:
                try:
                    await _call_task_center_api(request)
                except HTTPException:
                    # If task center call fails, rollback to draft status
                    task.status = TaskStatus.PENDING
                    task.publish_status = PublishStatus.DRAFT
                    db.commit()
                    raise
        
        # Return response
        return TaskPublishResponse(
            status=task.status.value,
            workflow_id=task.workflow_id,
            announcement_start=task.announcement_start,
            execution_start=task.execution_start,
            review_start=task.review_start,
            reward_start=task.reward_start,
            workflow_end=task.workflow_end,
            message="Task saved as draft" if publish_status == PublishStatus.DRAFT else "Task published successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error publishing task: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to publish task: {str(e)}")


async def _call_task_center_api(request: TaskPublishRequest):
    """Call task center API to publish task."""
    try:
        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key
        
        # Convert Pydantic model to dict with proper datetime serialization
        try:
            request_dict = request.model_dump(mode='json')
        except (AttributeError, TypeError) as e:
            logger.warning(f"Using fallback datetime serialization: {e}")
            request_dict = request.dict()
            
            # Recursively convert datetime objects to ISO format strings
            def convert_datetime(obj):
                if isinstance(obj, dict):
                    return {k: convert_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_datetime(item) for item in obj]
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                return obj
            
            request_dict = convert_datetime(request_dict)
        
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{task_center_url}/v1/tasks/publish",
                json=request_dict,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Task {request.workflow_id} published to task center successfully")
            return result
    except httpx.ConnectError as e:
        logger.error(f"Connection error publishing task to task center: Cannot connect to task_center at {task_center_url}. Error: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Task Center service is unavailable. Please ensure task_center is running at {task_center_url}"
        )
    except httpx.TimeoutException as e:
        logger.error(f"Timeout error publishing task to task center: Request to {task_center_url} timed out. Error: {e}")
        raise HTTPException(
            status_code=504,
            detail=f"Task Center request timed out. Please check if the service is running at {task_center_url}"
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to publish task to task center: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Failed to publish task to task center: {e.response.text}")
    except httpx.HTTPError as e:
        logger.error(f"HTTP error publishing task to task center: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to publish task to task center: {str(e)}")


@router.get("/{workflow_id}", response_model=TaskInfo)
async def get_task(workflow_id: str, db: Session = Depends(get_db)):
    try:
        task = db.query(Task).filter(Task.workflow_id == workflow_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Calculate display_status
        display_status = None
        if task.status == TaskStatus.PENDING or task.publish_status == PublishStatus.DRAFT:
            display_status = TaskStatus.NOT_STARTED.value
        elif task.status in [TaskStatus.ANNOUNCEMENT, TaskStatus.EXECUTION, TaskStatus.REVIEW, TaskStatus.REWARD]:
            display_status = TaskStatus.IN_PROGRESS.value
        elif task.status == TaskStatus.ENDED:
            display_status = TaskStatus.COMPLETED.value
        
        return TaskInfo(
            task_id=task.task_id,
            workflow_id=task.workflow_id,
            workflow_type=task.workflow_type.value,
            status=task.status.value,
            display_status=display_status,
            publish_status=task.publish_status.value,
            start_date=task.start_date,
            end_date=task.end_date,
            description=task.description,
            hf_dataset_url=task.hf_dataset_url,
            pdf_file_url=task.pdf_file_url,
            workflow_spec=task.workflow_spec,
            announcement_start=task.announcement_start,
            execution_start=task.execution_start,
            review_start=task.review_start,
            reward_start=task.reward_start,
            workflow_end=task.workflow_end,
            created_at=task.created_at
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get task: {str(e)}")


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    workflow_id: Optional[str] = None,
    status: Optional[str] = None,
    publish_status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    try:
        # Build query
        query = db.query(Task)
        
        # Apply filters
        if workflow_id:
            query = query.filter(Task.workflow_id == workflow_id)
        
        if status:
            try:
                task_status = TaskStatus(status)
                query = query.filter(Task.status == task_status)
            except ValueError:
                # Invalid status, ignore filter
                pass
        
        if publish_status:
            try:
                pub_status = PublishStatus(publish_status)
                query = query.filter(Task.publish_status == pub_status)
            except ValueError:
                # Invalid publish_status, ignore filter
                pass
        
        if workflow_type:
            query = query.filter(Task.workflow_type == workflow_type)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination
        tasks = query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        
        # Convert to TaskInfo
        workflows = []
        for task in tasks:
            # Calculate display_status
            display_status = None
            if task.status == TaskStatus.PENDING or task.publish_status == PublishStatus.DRAFT:
                display_status = TaskStatus.NOT_STARTED.value
            elif task.status in [TaskStatus.ANNOUNCEMENT, TaskStatus.EXECUTION, TaskStatus.REVIEW, TaskStatus.REWARD]:
                display_status = TaskStatus.IN_PROGRESS.value
            elif task.status == TaskStatus.ENDED:
                display_status = TaskStatus.COMPLETED.value
            
            workflows.append(TaskInfo(
                task_id=task.task_id,
                workflow_id=task.workflow_id,
                workflow_type=task.workflow_type.value,
                status=task.status.value,
                display_status=display_status,
                publish_status=task.publish_status.value,
                start_date=task.start_date,
                end_date=task.end_date,
                description=task.description,
                hf_dataset_url=task.hf_dataset_url,
                pdf_file_url=task.pdf_file_url,
                workflow_spec=task.workflow_spec,
                announcement_start=task.announcement_start,
                execution_start=task.execution_start,
                review_start=task.review_start,
                reward_start=task.reward_start,
                workflow_end=task.workflow_end,
                created_at=task.created_at
            ))
        
        # Build pagination info
        pagination = {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0
        }
        
        return TaskListResponse(
            workflows=workflows,
            pagination=pagination
        )
    except Exception as e:
        logger.error(f"Unexpected error listing tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")
