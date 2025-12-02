from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime


class MinerTaskReceive(BaseModel):
    workflow_id: str
    miner_key: str


class MinerTaskResponse(BaseModel):
    workflow_id: str
    workflow_spec: Dict[str, Any]
    deadline: datetime
    review_deadline: datetime
    
    @classmethod
    def from_task(cls, task):
        return cls(
            workflow_id=task.workflow_id,
            workflow_spec=task.workflow_spec,
            deadline=task.execution_start,
            review_deadline=task.review_start
        )


class MinerSubmitRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    workflow_id: str
    miner_key: str
    training_mode: str
    model_url: str
    model_metadata: Dict[str, Any]
    sample_images: Optional[list[str]] = None


class MinerSubmitResponse(BaseModel):
    submission_id: str
    workflow_id: str
    status: str
    estimated_reward: float

