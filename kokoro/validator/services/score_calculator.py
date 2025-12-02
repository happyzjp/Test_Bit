from typing import Dict, Any
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class ScoreCalculator:
    def __init__(self):
        pass
    
    def calculate_final_score(
        self,
        cosine_similarity: float,
        quality_score: float,
        time_coefficient: float = 1.0,
        constraint_coefficient: float = 1.0,
        k: int = 3
    ) -> float:
        base_score = cosine_similarity * 10.0
        
        quality_weight = (base_score ** k) * time_coefficient * constraint_coefficient
        
        if base_score < 3.5:
            return 0.0
        
        return quality_weight

