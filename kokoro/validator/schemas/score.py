from pydantic import BaseModel
from typing import Optional


class ScoreSubmitRequest(BaseModel):
    workflow_id: str
    miner_hotkey: str
    validator_hotkey: str
    cosine_similarity: Optional[float]
    quality_score: Optional[float]
    final_score: float


class ScoreSubmitResponse(BaseModel):
    status: str
    message: str

