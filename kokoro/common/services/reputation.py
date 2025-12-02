from typing import Dict, Optional
from datetime import datetime, timezone
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class ReputationService:
    """
    声誉系统服务
    
    根据文档7.7节：
    - EMA声誉分：使用指数移动平均计算声誉
    - 冷却机制：连续失败会被冷却，无法提交任务
    - 优先权：高声誉矿工在网络拥堵时拥有优先被审核权
    """
    
    def __init__(self, alpha: float = 0.9):
        """
        Args:
            alpha: 历史权重，默认0.9
        """
        self.alpha = alpha
    
    def calculate_reputation(
        self,
        previous_reputation: float,
        current_score: float
    ) -> float:
        """
        计算EMA声誉分
        
        公式：
        Reputation_t = α × Reputation_{t-1} + (1-α) × Current_Score
        
        其中：
        - α = 0.9（历史权重）
        - Current_Score：当前任务得分（0-10）
        """
        if current_score < 0 or current_score > 10:
            logger.warning(f"Invalid current_score: {current_score}, clamping to [0, 10]")
            current_score = max(0.0, min(10.0, current_score))
        
        reputation = self.alpha * previous_reputation + (1 - self.alpha) * current_score
        
        return max(0.0, min(10.0, reputation))
    
    def calculate_cooldown_hours(
        self,
        consecutive_failures: int
    ) -> int:
        """
        计算冷却时间（小时）
        
        冷却机制：
        - 1次失败：警告，不影响声誉
        - 2次失败：声誉降低10%
        - 3次失败：冷却24小时（无法提交任务）
        - 4次以上失败：冷却48小时
        """
        if consecutive_failures <= 1:
            return 0
        elif consecutive_failures == 2:
            return 0
        elif consecutive_failures == 3:
            return 24
        else:
            return 48
    
    def apply_reputation_penalty(
        self,
        current_reputation: float,
        consecutive_failures: int
    ) -> float:
        """
        应用声誉惩罚
        
        2次失败：声誉降低10%
        """
        if consecutive_failures >= 2:
            return current_reputation * 0.9
        return current_reputation
    
    def get_priority_level(self, reputation: float) -> str:
        """
        获取优先权级别
        
        在网络拥堵时：
        - 高声誉矿工（Reputation > 7.0）：优先被审核
        - 中等声誉矿工（Reputation 4.0-7.0）：正常审核
        - 低声誉矿工（Reputation < 4.0）：延迟审核
        """
        if reputation > 7.0:
            return "high"
        elif reputation >= 4.0:
            return "normal"
        else:
            return "low"
    
    def should_allow_submission(
        self,
        reputation: float,
        consecutive_failures: int,
        last_failure_time: Optional[datetime] = None
    ) -> bool:
        """
        判断是否允许提交任务
        
        考虑因素：
        1. 冷却时间是否已过
        2. 声誉是否足够
        """
        cooldown_hours = self.calculate_cooldown_hours(consecutive_failures)
        
        if cooldown_hours == 0:
            return True
        
        if last_failure_time is None:
            return True
        
        now = datetime.now(timezone.utc)
        time_since_failure = (now - last_failure_time).total_seconds() / 3600
        
        return time_since_failure >= cooldown_hours

