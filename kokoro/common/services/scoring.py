from typing import Dict, Optional
from datetime import datetime, timezone
from kokoro.common.utils.time import calculate_time_coefficient
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class ScoringService:
    def __init__(self, k: int = 3, baseline: float = 3.5):
        self.k = k
        self.baseline = baseline
    
    def calculate_quality_score(self, score: float) -> float:
        if score < self.baseline:
            return 0.0
        return score ** self.k
    
    def calculate_time_coefficient(
        self,
        submit_time: datetime,
        execution_start: datetime,
        execution_end: datetime
    ) -> float:
        return calculate_time_coefficient(submit_time, execution_start, execution_end)
    
    def calculate_constraint_coefficient(
        self,
        file_size_mb: Optional[float] = None,
        vram_gb: Optional[float] = None,
        inference_time_seconds: Optional[float] = None
    ) -> float:
        coefficient = 1.0
        
        if file_size_mb and file_size_mb > 50:
            coefficient *= 0.8
        
        if vram_gb and vram_gb > 16:
            coefficient *= 0.7
        
        if inference_time_seconds and inference_time_seconds > 10:
            coefficient *= 0.9
        
        return max(0.5, coefficient)
    
    def calculate_final_weight(
        self,
        quality_score: float,
        time_coefficient: float,
        constraint_coefficient: float
    ) -> float:
        if quality_score == 0.0:
            return 0.0
        
        return quality_score * time_coefficient * constraint_coefficient
    
    def calculate_reward(
        self,
        miner_weight: float,
        total_weights: float,
        total_emission: float,
        task_type: str
    ) -> float:
        """
        计算单个矿工的奖励
        
        根据文档7.2节：
        - 文本LoRA任务池 = 总排放 × 27%
        - 图像LoRA任务池 = 总排放 × 63%
        
        Args:
            miner_weight: 矿工权重
            total_weights: 总权重
            total_emission: 当日总排放量
            task_type: 任务类型
        
        Returns:
            矿工奖励（TAO）
        """
        if total_weights == 0:
            return 0.0
        
        if task_type == "text_lora_creation":
            task_pool = total_emission * 0.27
        elif task_type == "image_lora_creation":
            task_pool = total_emission * 0.63
        else:
            task_pool = total_emission * 0.45
        
        return (miner_weight / total_weights) * task_pool

