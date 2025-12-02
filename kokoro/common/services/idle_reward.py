from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from kokoro.common.utils.logging import setup_logger
import statistics

logger = setup_logger(__name__)


class IdleRewardService:
    """
    无任务期间的奖励分配服务
    
    根据文档7.8节：
    - 无任务期间：100% 系统排放划入系统金库
    - 矿工不获得任何奖励
    - 但需要计算 K_Critical 和 R_Hardware 用于节点质量评估
    """
    
    def __init__(self):
        pass
    
    def calculate_k_critical(
        self,
        latency_ms: float,
        packet_loss_percent: float
    ) -> float:
        """
        计算严苛门槛系数 K_Critical
        
        公式：
        K_Critical = {
            1.0  if Latency <= 150ms AND PacketLoss <= 1%
            0.5  if 150ms < Latency <= 400ms
            0.0  if Latency > 400ms OR PacketLoss > 1%
        }
        
        目的：确保奖励不流向使用家庭宽带或廉价拥堵 VPS 的节点
        """
        if packet_loss_percent > 1.0:
            return 0.0
        
        if latency_ms <= 150 and packet_loss_percent <= 1.0:
            return 1.0
        elif 150 < latency_ms <= 400:
            return 0.5
        else:
            return 0.0
    
    def calculate_r_hardware(
        self,
        jitter_scores: List[float],
        uptime_streak_days: int
    ) -> float:
        """
        计算硬件稳定性声誉 R_Hardware
        
        公式：
        R_Hardware = Score_Jitter × Score_Streak
        
        计算维度：
        1. Jitter (网络抖动)：基于最近 N 次心跳的方差，抖动越小得分越高
        2. Uptime Streak：连续在线 7 天无中断得满分
        
        意义：这是对"投入真金白银租好服务器"的矿工的直接补贴
        """
        if not jitter_scores:
            return 0.0
        
        jitter_variance = statistics.variance(jitter_scores) if len(jitter_scores) > 1 else 0.0
        
        score_jitter = self._calculate_jitter_score(jitter_variance)
        score_streak = self._calculate_streak_score(uptime_streak_days)
        
        return score_jitter * score_streak
    
    def _calculate_jitter_score(self, jitter_variance: float) -> float:
        """
        计算Jitter得分
        
        抖动越小（企业级专线），得分越高
        """
        if jitter_variance <= 1.0:
            return 1.0
        elif jitter_variance <= 5.0:
            return 0.8
        elif jitter_variance <= 10.0:
            return 0.6
        elif jitter_variance <= 20.0:
            return 0.4
        else:
            return 0.2
    
    def _calculate_streak_score(self, uptime_streak_days: int) -> float:
        """
        计算Uptime Streak得分
        
        连续在线 7 天无中断得满分
        """
        if uptime_streak_days >= 7:
            return 1.0
        elif uptime_streak_days >= 5:
            return 0.8
        elif uptime_streak_days >= 3:
            return 0.6
        elif uptime_streak_days >= 1:
            return 0.4
        else:
            return 0.2
    
    def calculate_idle_rewards(
        self,
        total_emission: float,
        miner_metrics: Dict[str, Dict]
    ) -> Dict[str, float]:
        """
        计算无任务期间的奖励分配
        
        根据文档：
        - 100% 系统排放划入系统金库
        - 矿工不获得任何奖励
        
        但返回矿工的质量评估指标（K_Critical 和 R_Hardware）
        """
        treasury_amount = total_emission * 1.0
        
        rewards = {}
        for miner_hotkey, metrics in miner_metrics.items():
            k_critical = self.calculate_k_critical(
                metrics.get("latency_ms", 0.0),
                metrics.get("packet_loss_percent", 0.0)
            )
            
            r_hardware = self.calculate_r_hardware(
                metrics.get("jitter_scores", []),
                metrics.get("uptime_streak_days", 0)
            )
            
            if k_critical == 0.0:
                rewards[miner_hotkey] = 0.0
            else:
                rewards[miner_hotkey] = 0.0
        
        logger.info(f"Idle period: {treasury_amount} TAO allocated to treasury, 0 TAO to miners")
        
        return {
            "treasury": treasury_amount,
            "miner_rewards": rewards
        }

