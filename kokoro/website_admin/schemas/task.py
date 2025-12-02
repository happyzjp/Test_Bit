from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class DatasetSpec(BaseModel):
    source: str = "huggingface"
    repository_id: str
    sample_count: int
    data_format: Optional[str] = "jsonl"
    question_column: Optional[str] = None
    answer_column: Optional[str] = None
    image_column: Optional[str] = None
    caption_column: Optional[str] = None


class TrainingSpec(BaseModel):
    base_model: str
    lora_rank: int = 16
    lora_alpha: int = 32
    iteration_count: int = 1000
    batch_size: int = 4
    learning_rate: float = 2e-4
    max_length: Optional[int] = 512
    resolution: Optional[List[int]] = None


class WorkflowSpec(BaseModel):
    theme: str
    target_platform: str
    deployment_target: str
    training_mode: str = Field(..., description="new or incremental")
    dataset_spec: DatasetSpec
    training_spec: TrainingSpec
    base_lora_url: Optional[str] = None


class TaskPublishRequest(BaseModel):
    task_id: Optional[str] = None  # User-defined task ID
    workflow_id: str
    workflow_type: str = Field(..., description="text_lora_creation or image_lora_creation")
    workflow_spec: WorkflowSpec
    publish_status: Optional[str] = "draft"  # 草稿/已发布，默认草稿
    start_date: Optional[datetime] = None  # Start Date
    end_date: Optional[datetime] = None  # End Date
    description: Optional[str] = None  # 描述
    hf_dataset_url: Optional[str] = None  # 训练数据集HF的URL
    pdf_file_url: Optional[str] = None  # PDF任务文件URL
    announcement_duration: float = Field(..., description="Duration in days")
    execution_duration: float = Field(..., description="Duration in days")
    review_duration: float = Field(..., description="Duration in days")
    reward_duration: float = Field(default=0.0, description="Duration in days")


class TaskPublishResponse(BaseModel):
    status: str
    workflow_id: str
    announcement_start: Optional[datetime]
    execution_start: Optional[datetime]
    review_start: Optional[datetime]
    reward_start: Optional[datetime]
    workflow_end: Optional[datetime]
    message: str


class TaskQueryRequest(BaseModel):
    workflow_id: Optional[str] = None
    status: Optional[str] = None
    workflow_type: Optional[str] = None
    page: int = 1
    page_size: int = 20


class TaskInfo(BaseModel):
    task_id: Optional[str] = None  # User-defined task ID
    workflow_id: str
    workflow_type: str
    status: str
    display_status: Optional[str] = None  # not_started/in_progress/completed
    publish_status: Optional[str] = "draft"  # 草稿/已发布
    start_date: Optional[datetime] = None  # Start Date
    end_date: Optional[datetime] = None  # End Date
    description: Optional[str] = None  # 描述
    hf_dataset_url: Optional[str] = None  # 训练数据集HF的URL
    pdf_file_url: Optional[str] = None  # PDF任务文件URL
    workflow_spec: Optional[Dict[str, Any]] = None  # Workflow specification JSON
    announcement_start: Optional[datetime] = None
    execution_start: Optional[datetime] = None
    review_start: Optional[datetime] = None
    reward_start: Optional[datetime] = None
    workflow_end: Optional[datetime] = None
    created_at: Optional[datetime] = None


class TaskListResponse(BaseModel):
    workflows: List[TaskInfo]
    pagination: Dict[str, Any]
