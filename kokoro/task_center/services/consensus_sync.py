from sqlalchemy.orm import Session
from typing import Dict, List
from kokoro.task_center.services.score_archive import ScoreArchive
from kokoro.common.utils.logging import setup_logger
import statistics
import httpx
from kokoro.common.config import settings

logger = setup_logger(__name__)


class ConsensusSync:
    def __init__(self, db: Session):
        self.db = db
        self.score_archive = ScoreArchive(db)
    
    def aggregate_scores(self, workflow_id: str) -> Dict[str, float]:
        all_scores = self.score_archive.get_all_scores_for_workflow(workflow_id)
        
        miner_aggregated = {}
        for miner_data in all_scores:
            miner_hotkey = miner_data["miner_hotkey"]
            scores = [s["final_score"] for s in miner_data["scores"]]
            
            if len(scores) >= 3:
                scores_sorted = sorted(scores)
                scores_filtered = scores_sorted[1:-1]
                avg_score = statistics.mean(scores_filtered)
            else:
                avg_score = statistics.mean(scores) if scores else 0.0
            
            miner_aggregated[miner_hotkey] = avg_score
        
        return miner_aggregated
    
    def sync_consensus_data(self, workflow_id: str) -> Dict[str, Dict]:
        aggregated_scores = self.aggregate_scores(workflow_id)
        
        return {
            "workflow_id": workflow_id,
            "miner_scores": aggregated_scores,
            "consensus_status": "completed"
        }
    
    async def notify_validators(self, workflow_id: str, consensus_data: Dict):
        from kokoro.common.models.validator import Validator
        validators = self.db.query(Validator).filter(Validator.is_active == True).all()
        
        for validator in validators:
            try:
                validator_url = f"http://{validator.hotkey}:8000"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f"{validator_url}/v1/consensus/sync",
                        json={
                            "workflow_id": workflow_id,
                            "consensus_data": consensus_data
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to notify validator {validator.hotkey}: {e}")

