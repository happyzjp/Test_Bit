from typing import Dict, List, Optional
from kokoro.common.services.scoring import ScoringService
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class RewardService:
    """
    奖励分配服务
    
    根据文档7.2节：
    - 有任务期间：10% 系统金库，90% 矿工池
    - 文本LoRA任务：矿工池的30% = 总排放的27%
    - 图像LoRA任务：矿工池的70% = 总排放的63%
    """
    
    def __init__(self):
        self.scoring_service = ScoringService()
    
    def calculate_rewards(
        self,
        miner_scores: Dict[str, float],
        miner_weights: Optional[Dict[str, float]] = None,
        task_type: str = "text_lora_creation",
        total_emission: float = 1000.0
    ) -> Dict[str, float]:
        """
        计算有任务期间的奖励分配
        
        Args:
            miner_scores: 矿工质量得分字典 {hotkey: score}
            miner_weights: 矿工权重字典 {hotkey: weight}，如果提供则直接使用
            task_type: 任务类型 ("text_lora_creation" 或 "image_lora_creation")
            total_emission: 当日总排放量（TAO）
        
        Returns:
            矿工奖励字典 {hotkey: reward}
        """
        treasury_amount = total_emission * 0.10
        miner_pool = total_emission * 0.90
        
        if task_type == "text_lora_creation":
            task_pool = total_emission * 0.27
        elif task_type == "image_lora_creation":
            task_pool = total_emission * 0.63
        else:
            task_pool = miner_pool * 0.50
        
        if miner_weights:
            weights = miner_weights
        else:
            weights = {}
            for miner_hotkey, score in miner_scores.items():
                if score < 3.5:
                    weights[miner_hotkey] = 0.0
                else:
                    weights[miner_hotkey] = self.scoring_service.calculate_quality_score(score)
        
        total_weight = sum(weights.values())
        
        if total_weight == 0:
            logger.warning("Total weight is 0, no rewards allocated")
            return {hotkey: 0.0 for hotkey in miner_scores.keys()}
        
        rewards = {}
        for miner_hotkey, weight in weights.items():
            if weight == 0.0:
                rewards[miner_hotkey] = 0.0
            else:
                reward = (weight / total_weight) * task_pool
                rewards[miner_hotkey] = reward
        
        logger.info(
            f"Reward calculation: treasury={treasury_amount:.2f} TAO, "
            f"task_pool={task_pool:.2f} TAO, "
            f"total_weight={total_weight:.2f}, "
            f"task_type={task_type}"
        )
        
        return rewards
    
    def calculate_idle_rewards(
        self,
        total_emission: float
    ) -> Dict[str, float]:
        """
        计算无任务期间的奖励分配
        
        根据文档7.8节：
        - 100% 系统排放划入系统金库
        - 矿工不获得任何奖励
        
        Returns:
            {"treasury": amount, "miner_rewards": {}}
        """
        treasury_amount = total_emission * 1.0
        
        logger.info(f"Idle period: {treasury_amount:.2f} TAO allocated to treasury, 0 TAO to miners")
        
        return {
            "treasury": treasury_amount,
            "miner_rewards": {}
        }

