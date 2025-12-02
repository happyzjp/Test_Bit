from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from kokoro.common.models.task import TaskStatus, Task


class WorkflowSpec(BaseModel):
    theme: str
    target_platform: str
    deployment_target: str
    training_mode: str
    dataset_spec: Dict[str, Any]
    training_spec: Dict[str, Any]
    base_lora_url: Optional[str] = None


class TaskCreate(BaseModel):
    task_id: Optional[str] = None  # User-defined task ID
    workflow_id: str
    workflow_type: str
    workflow_spec: WorkflowSpec
    publish_status: Optional[str] = "draft"  # 草稿/已发布，默认草稿
    start_date: Optional[datetime] = None  # Start Date
    end_date: Optional[datetime] = None  # End Date
    description: Optional[str] = None  # 描述
    hf_dataset_url: Optional[str] = None  # 训练数据集HF的URL
    pdf_file_url: Optional[str] = None  # PDF任务文件URL
    announcement_duration: float
    execution_duration: float
    review_duration: float
    reward_duration: float


class TaskResponse(BaseModel):
    task_id: Optional[str] = None  # User-defined task ID
    workflow_id: str
    workflow_type: str
    status: TaskStatus
    display_status: Optional[str] = None  # not_started/in_progress/completed
    publish_status: Optional[str] = "draft"  # 草稿/已发布
    start_date: Optional[datetime] = None  # Start Date
    end_date: Optional[datetime] = None  # End Date
    description: Optional[str] = None  # 描述
    hf_dataset_url: Optional[str] = None  # 训练数据集HF的URL
    pdf_file_url: Optional[str] = None  # PDF任务文件URL
    announcement_start: Optional[datetime] = None
    execution_start: Optional[datetime] = None
    review_start: Optional[datetime] = None
    reward_start: Optional[datetime] = None
    workflow_end: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_orm(cls, task):
        # Calculate display_status based on status
        display_status = None
        if hasattr(task, 'status'):
            if task.status == TaskStatus.PENDING or task.status == TaskStatus.NOT_STARTED:
                display_status = TaskStatus.NOT_STARTED.value
            elif task.status in [TaskStatus.ANNOUNCEMENT, TaskStatus.EXECUTION, TaskStatus.REVIEW, TaskStatus.REWARD, TaskStatus.IN_PROGRESS]:
                display_status = TaskStatus.IN_PROGRESS.value
            elif task.status in [TaskStatus.ENDED, TaskStatus.COMPLETED]:
                display_status = TaskStatus.COMPLETED.value
        
        return cls(
            task_id=getattr(task, 'task_id', None),
            workflow_id=task.workflow_id,
            workflow_type=task.workflow_type,
            status=task.status,
            display_status=display_status,
            publish_status=getattr(task, 'publish_status', 'draft'),
            start_date=getattr(task, 'start_date', None),
            end_date=getattr(task, 'end_date', None),
            description=getattr(task, 'description', None),
            hf_dataset_url=getattr(task, 'hf_dataset_url', None),
            pdf_file_url=getattr(task, 'pdf_file_url', None),
            announcement_start=task.announcement_start,
            execution_start=task.execution_start,
            review_start=task.review_start,
            reward_start=task.reward_start,
            workflow_end=task.workflow_end,
            created_at=getattr(task, 'created_at', None)
        )


class TaskListResponse(BaseModel):
    workflows: list[TaskResponse]
    pagination: Dict[str, Any]

