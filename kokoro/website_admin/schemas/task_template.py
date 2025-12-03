from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class TaskTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    workflow_type: str
    workflow_spec: Dict[str, Any]
    announcement_duration: Optional[str] = "0.25"
    execution_duration: Optional[str] = "3.0"
    review_duration: Optional[str] = "1.0"
    reward_duration: Optional[str] = "0.0"
    is_active: Optional[bool] = True


class TaskTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    workflow_spec: Optional[Dict[str, Any]] = None
    announcement_duration: Optional[str] = None
    execution_duration: Optional[str] = None
    review_duration: Optional[str] = None
    reward_duration: Optional[str] = None
    is_active: Optional[bool] = None


class TaskTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    workflow_type: str
    workflow_spec: Dict[str, Any]
    announcement_duration: str
    execution_duration: str
    review_duration: str
    reward_duration: str
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskTemplateListResponse(BaseModel):
    templates: list[TaskTemplateResponse]
    total: int

