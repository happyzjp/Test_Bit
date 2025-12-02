from typing import Dict, List, Any
from kokoro.common.utils.logging import setup_logger
from kokoro.task_center.services.consensus_sync import ConsensusSync
from kokoro.common.database import get_db
import statistics

logger = setup_logger(__name__)


class ConsensusManager:
    def __init__(self):
        pass
    
    def submit_consensus_weights(
        self,
        workflow_id: str,
        validator_key: str,
        weights: Dict[str, float]
    ) -> Dict[str, Any]:
        from kokoro.common.database import SessionLocal
        db = SessionLocal()
        try:
            consensus_sync = ConsensusSync(db)
            consensus_data = consensus_sync.sync_consensus_data(workflow_id)
            
            validator_weights = {}
            for miner_hotkey, weight in weights.items():
                validator_weights[miner_hotkey] = weight
            
            final_weights = self._calculate_final_weights(
                workflow_id,
                validator_weights,
                consensus_data.get("miner_scores", {})
            )
            
            return {
                "workflow_id": workflow_id,
                "validator_key": validator_key,
                "final_weights": final_weights,
                "consensus_status": "completed"
            }
        finally:
            db.close()
    
    def _calculate_final_weights(
        self,
        workflow_id: str,
        validator_weights: Dict[str, float],
        miner_scores: Dict[str, float]
    ) -> Dict[str, float]:
        all_miner_hotkeys = set(list(validator_weights.keys()) + list(miner_scores.keys()))
        
        final_weights = {}
        
        for miner_hotkey in all_miner_hotkeys:
            weight_list = []
            
            if miner_hotkey in validator_weights:
                weight_list.append(validator_weights[miner_hotkey])
            
            if miner_hotkey in miner_scores:
                score = miner_scores[miner_hotkey]
                if score >= 3.5:
                    weight_list.append(score ** 3)
            
            if len(weight_list) >= 3:
                sorted_weights = sorted(weight_list)
                filtered_weights = sorted_weights[1:-1]
                avg_weight = statistics.mean(filtered_weights)
            elif len(weight_list) > 0:
                avg_weight = statistics.mean(weight_list)
            else:
                avg_weight = 0.0
            
            final_weights[miner_hotkey] = avg_weight
        
        total_weight = sum(final_weights.values())
        if total_weight > 0:
            final_weights = {
                hotkey: weight / total_weight
                for hotkey, weight in final_weights.items()
            }
        
        return final_weights

