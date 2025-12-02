from pydantic import BaseModel
from typing import Dict


class WeightCalculateRequest(BaseModel):
    workflow_id: str
    miner_scores: Dict[str, float]


class WeightCalculateResponse(BaseModel):
    weights: Dict[str, float]

