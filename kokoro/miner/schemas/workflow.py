from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime


class WorkflowReceive(BaseModel):
    workflow_id: str
    miner_key: str


class WorkflowReceiveResponse(BaseModel):
    workflow_id: str
    workflow_spec: Dict[str, Any]
    deadline: datetime
    review_deadline: datetime


class WorkflowSubmit(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    workflow_id: str
    miner_key: str
    training_mode: str
    model_url: str
    model_metadata: Dict[str, Any]
    sample_images: Optional[list[str]] = None


class WorkflowSubmitResponse(BaseModel):
    submission_id: str
    workflow_id: str
    status: str
    estimated_reward: float

