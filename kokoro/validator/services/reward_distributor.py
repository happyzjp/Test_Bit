from typing import Dict, List, Optional
from datetime import datetime, timezone
from kokoro.common.services.reward import RewardService
from kokoro.common.services.idle_reward import IdleRewardService
from kokoro.common.services.scoring import ScoringService
from kokoro.common.bittensor.client import BittensorClient
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class RewardDistributor:
    """
    奖励分配器
    
    根据文档7.9节：
    - 任务期间：即时分配（评分共识达成后立即触发）
    - 无任务期间：每24小时分配一次（基于历史表现）
    """
    
    def __init__(self, bittensor_client: BittensorClient):
        self.bittensor_client = bittensor_client
        self.reward_service = RewardService()
        self.idle_reward_service = IdleRewardService()
        self.scoring_service = ScoringService()
    
    def distribute_task_rewards(
        self,
        workflow_id: str,
        miner_scores: Dict[str, float],
        miner_weights: Optional[Dict[str, float]] = None,
        miner_submit_times: Optional[Dict[str, datetime]] = None,
        execution_start: Optional[datetime] = None,
        execution_end: Optional[datetime] = None,
        task_type: str = "text_lora_creation"
    ) -> Dict[str, float]:
        """
        分配任务期间的奖励
        
        根据文档7.2节和7.9节：
        - 即时分配：评分共识达成后立即触发合约分账
        - 权重瓜分制：Weight = S_quality^k × M_time × M_constraint
        - 任务类型差异化：文本27%，图像63%
        """
        total_emission = self.bittensor_client.get_emission()
        
        if miner_weights is None:
            miner_weights = {}
            for miner_hotkey, score in miner_scores.items():
                if score < 3.5:
                    miner_weights[miner_hotkey] = 0.0
                    continue
                
                quality_score = self.scoring_service.calculate_quality_score(score)
                
                time_coefficient = 1.0
                if miner_submit_times and execution_start and execution_end:
                    submit_time = miner_submit_times.get(miner_hotkey)
                    if submit_time:
                        time_coefficient = self.scoring_service.calculate_time_coefficient(
                            submit_time, execution_start, execution_end
                        )
                
                constraint_coefficient = 1.0
                
                final_weight = self.scoring_service.calculate_final_weight(
                    quality_score,
                    time_coefficient,
                    constraint_coefficient
                )
                
                miner_weights[miner_hotkey] = final_weight
        
        rewards = self.reward_service.calculate_rewards(
            miner_scores=miner_scores,
            miner_weights=miner_weights,
            task_type=task_type,
            total_emission=total_emission
        )
        
        logger.info(
            f"Task rewards distributed for workflow {workflow_id}: "
            f"{len([r for r in rewards.values() if r > 0])} miners received rewards"
        )
        
        return rewards
    
    def distribute_idle_rewards(
        self,
        miner_metrics: Optional[Dict[str, Dict]] = None
    ) -> Dict[str, float]:
        """
        分配无任务期间的奖励
        
        根据文档7.8节：
        - 100% 系统排放划入系统金库
        - 矿工不获得任何奖励
        - 但需要计算 K_Critical 和 R_Hardware 用于节点质量评估
        """
        total_emission = self.bittensor_client.get_emission()
        
        result = self.reward_service.calculate_idle_rewards(total_emission)
        
        if miner_metrics:
            for miner_hotkey, metrics in miner_metrics.items():
                k_critical = self.idle_reward_service.calculate_k_critical(
                    metrics.get("latency_ms", 0.0),
                    metrics.get("packet_loss_percent", 0.0)
                )
                
                r_hardware = self.idle_reward_service.calculate_r_hardware(
                    metrics.get("jitter_scores", []),
                    metrics.get("uptime_streak_days", 0)
                )
                
                logger.debug(
                    f"Miner {miner_hotkey}: K_Critical={k_critical:.2f}, "
                    f"R_Hardware={r_hardware:.2f}"
                )
        
        logger.info(
            f"Idle period rewards: {result['treasury']:.2f} TAO to treasury, "
            f"0 TAO to miners"
        )
        
        return result

