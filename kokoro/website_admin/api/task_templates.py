from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
from kokoro.common.database import get_db
from kokoro.website_admin.models.task_template import TaskTemplate
from kokoro.website_admin.schemas.task_template import (
    TaskTemplateCreate, TaskTemplateUpdate, TaskTemplateResponse, TaskTemplateListResponse
)
from kokoro.common.utils.logging import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


@router.post("", response_model=TaskTemplateResponse)
async def create_template(
    template_data: TaskTemplateCreate,
    db: Session = Depends(get_db)
):
    """Create a new task template."""
    try:
        # Check if template with same name already exists
        existing = db.query(TaskTemplate).filter(TaskTemplate.name == template_data.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Template with this name already exists")
        
        template = TaskTemplate(
            name=template_data.name,
            description=template_data.description,
            workflow_type=template_data.workflow_type,
            workflow_spec=template_data.workflow_spec,
            announcement_duration=template_data.announcement_duration,
            execution_duration=template_data.execution_duration,
            review_duration=template_data.review_duration,
            reward_duration=template_data.reward_duration,
            is_active=template_data.is_active
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        logger.info(f"Task template created: {template.name} (ID: {template.id})")
        return TaskTemplateResponse.model_validate(template)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating task template: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")


@router.get("", response_model=TaskTemplateListResponse)
async def list_templates(
    workflow_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all task templates."""
    try:
        query = db.query(TaskTemplate)
        
        if workflow_type:
            query = query.filter(TaskTemplate.workflow_type == workflow_type)
        if is_active is not None:
            query = query.filter(TaskTemplate.is_active == is_active)
        
        total = query.count()
        templates = query.offset(skip).limit(limit).all()
        
        return TaskTemplateListResponse(
            templates=[TaskTemplateResponse.model_validate(t) for t in templates],
            total=total
        )
        
    except Exception as e:
        logger.error(f"Error listing task templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list templates: {str(e)}")


@router.get("/{template_id}", response_model=TaskTemplateResponse)
async def get_template(
    template_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific task template by ID."""
    try:
        template = db.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        return TaskTemplateResponse.model_validate(template)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@router.put("/{template_id}", response_model=TaskTemplateResponse)
async def update_template(
    template_id: int,
    template_data: TaskTemplateUpdate,
    db: Session = Depends(get_db)
):
    """Update a task template."""
    try:
        template = db.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        if template_data.name is not None:
            # Check if new name conflicts with another template
            existing = db.query(TaskTemplate).filter(
                TaskTemplate.name == template_data.name,
                TaskTemplate.id != template_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Template with this name already exists")
            template.name = template_data.name
        
        if template_data.description is not None:
            template.description = template_data.description
        if template_data.workflow_spec is not None:
            template.workflow_spec = template_data.workflow_spec
        if template_data.announcement_duration is not None:
            template.announcement_duration = template_data.announcement_duration
        if template_data.execution_duration is not None:
            template.execution_duration = template_data.execution_duration
        if template_data.review_duration is not None:
            template.review_duration = template_data.review_duration
        if template_data.reward_duration is not None:
            template.reward_duration = template_data.reward_duration
        if template_data.is_active is not None:
            template.is_active = template_data.is_active
        
        db.commit()
        db.refresh(template)
        
        logger.info(f"Task template updated: {template.name} (ID: {template.id})")
        return TaskTemplateResponse.model_validate(template)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task template: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: Session = Depends(get_db)
):
    """Delete a task template."""
    try:
        template = db.query(TaskTemplate).filter(TaskTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        db.delete(template)
        db.commit()
        
        logger.info(f"Task template deleted: {template.name} (ID: {template.id})")
        return {"message": "Template deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task template: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")

