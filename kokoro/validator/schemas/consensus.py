from pydantic import BaseModel
from typing import Dict, Any


class ConsensusWeightRequest(BaseModel):
    workflow_id: str
    validator_key: str
    weights: Dict[str, float]


class ConsensusWeightResponse(BaseModel):
    workflow_id: str
    validator_key: str
    final_weights: Dict[str, float]
    consensus_status: str


class ConsensusSyncRequest(BaseModel):
    workflow_id: str
    consensus_data: Dict[str, Any]

