from typing import Dict, List
from kokoro.common.utils.logging import setup_logger
from kokoro.common.services.scoring import ScoringService
from kokoro.common.services.reward import RewardService
from kokoro.validator.services.bittensor_sync import BittensorSyncService
from kokoro.common.bittensor.wallet import WalletManager

logger = setup_logger(__name__)


class WeightCalculator:
    def __init__(self, bittensor_sync: BittensorSyncService):
        self.scoring_service = ScoringService()
        self.reward_service = RewardService()
        self.bittensor_sync = bittensor_sync
    
    def calculate_weights(
        self,
        workflow_id: str,
        miner_scores: Dict[str, float],
        miner_submit_times: Dict[str, float] = None,
        execution_start: float = None,
        execution_end: float = None
    ) -> Dict[str, float]:
        weights = {}
        
        for hotkey, score in miner_scores.items():
            if score < 3.5:
                weights[hotkey] = 0.0
                continue
            
            quality_weight = self.scoring_service.calculate_quality_score(score)
            
            time_coefficient = 1.0
            if miner_submit_times and execution_start and execution_end:
                from datetime import datetime, timezone
                submit_time = datetime.fromtimestamp(miner_submit_times[hotkey], timezone.utc)
                exec_start = datetime.fromtimestamp(execution_start, timezone.utc)
                exec_end = datetime.fromtimestamp(execution_end, timezone.utc)
                time_coefficient = self.scoring_service.calculate_time_coefficient(
                    submit_time, exec_start, exec_end
                )
            
            constraint_coefficient = 1.0
            
            final_weight = self.scoring_service.calculate_final_weight(
                quality_weight,
                time_coefficient,
                constraint_coefficient
            )
            
            weights[hotkey] = final_weight
        
        total_weight = sum(weights.values())
        
        if total_weight == 0:
            return {hotkey: 0.0 for hotkey in miner_scores.keys()}
        
        normalized_weights = {}
        for hotkey, weight in weights.items():
            normalized_weights[hotkey] = weight / total_weight
        
        return normalized_weights
    
    def set_weights_to_chain(self, weights: Dict[str, float]):
        logger.info(f"Setting weights to chain: {len(weights)} miners")
        
        try:
            miners = self.bittensor_sync.get_all_miners()
            hotkey_to_uid = {miner["hotkey"]: miner["uid"] for miner in miners}
            
            uids = []
            weight_values = []
            
            for hotkey, weight in weights.items():
                if hotkey in hotkey_to_uid:
                    uids.append(hotkey_to_uid[hotkey])
                    weight_values.append(weight)
            
            if uids:
                self.bittensor_sync.set_weights(uids, weight_values)
                logger.info(f"Weights set successfully: {len(uids)} miners")
            else:
                logger.warning("No valid miners found for weight setting")
        except Exception as e:
            logger.error(f"Failed to set weights to chain: {e}")
            raise

