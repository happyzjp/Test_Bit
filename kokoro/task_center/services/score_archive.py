from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Optional
from kokoro.common.models.score import Score
from kokoro.task_center.schemas.score import ScoreSubmit
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class ScoreArchive:
    def __init__(self, db: Session):
        self.db = db
    
    def submit_score(self, score_data: ScoreSubmit):
        score = Score(
            workflow_id=score_data.workflow_id,
            miner_hotkey=score_data.miner_hotkey,
            validator_hotkey=score_data.validator_hotkey,
            cosine_similarity=score_data.cosine_similarity,
            quality_score=score_data.quality_score,
            final_score=score_data.final_score
        )
        
        self.db.add(score)
        self.db.commit()
        
        logger.info(f"Score submitted: miner={score_data.miner_hotkey}, score={score_data.final_score}")
        
        from kokoro.task_center.services.continuous_reward_distributor import ContinuousRewardDistributor
        
        from kokoro.common.models.audit_task import AuditTask
        audit_tasks = self.db.query(AuditTask).filter(
            AuditTask.original_task_id == score_data.workflow_id,
            AuditTask.miner_hotkey == score_data.miner_hotkey
        ).all()
        
        completed_audits = [t for t in audit_tasks if t.is_completed]
        
        if len(completed_audits) >= 3:
            latest_audit = max(completed_audits, key=lambda x: x.completed_at or x.created_at)
            
            reward_distributor = ContinuousRewardDistributor(self.db)
            try:
                rewards = reward_distributor.distribute_rewards_for_completed_audit(
                    latest_audit.audit_task_id,
                    score_data.workflow_id
                )
                logger.info(
                    f"Rewards distributed after consensus reached for workflow {score_data.workflow_id}: "
                    f"{len([r for r in rewards.values() if r > 0])} miners received rewards"
                )
            except Exception as e:
                logger.error(f"Failed to distribute rewards: {e}", exc_info=True)
    
    def get_miner_scores(
        self,
        miner_hotkey: str,
        workflow_id: Optional[str] = None
    ) -> List[Dict]:
        query = self.db.query(Score).filter(Score.miner_hotkey == miner_hotkey)
        
        if workflow_id:
            query = query.filter(Score.workflow_id == workflow_id)
        
        scores = query.all()
        
        return [
            {
                "workflow_id": s.workflow_id,
                "validator_hotkey": s.validator_hotkey,
                "cosine_similarity": s.cosine_similarity,
                "quality_score": s.quality_score,
                "final_score": s.final_score,
                "created_at": s.created_at.isoformat()
            }
            for s in scores
        ]
    
    def calculate_ema_score(
        self,
        miner_hotkey: str,
        workflow_id: Optional[str] = None,
        alpha: float = 0.9
    ) -> float:
        scores = self.get_miner_scores(miner_hotkey, workflow_id)
        
        if not scores:
            return 0.0
        
        ema_score = scores[0]["final_score"]
        for score in scores[1:]:
            ema_score = alpha * ema_score + (1 - alpha) * score["final_score"]
        
        return ema_score
    
    def get_all_scores_for_workflow(self, workflow_id: str) -> List[Dict]:
        scores = self.db.query(Score).filter(Score.workflow_id == workflow_id).all()
        
        miner_scores = {}
        for score in scores:
            if score.miner_hotkey not in miner_scores:
                miner_scores[score.miner_hotkey] = []
            
            miner_scores[score.miner_hotkey].append({
                "validator_hotkey": score.validator_hotkey,
                "cosine_similarity": score.cosine_similarity,
                "quality_score": score.quality_score,
                "final_score": score.final_score,
                "created_at": score.created_at.isoformat()
            })
        
        result = []
        for miner_hotkey, score_list in miner_scores.items():
            if len(score_list) >= 3:
                import statistics
                scores_sorted = sorted([s["final_score"] for s in score_list])
                scores_filtered = scores_sorted[1:-1]
                avg_score = statistics.mean(scores_filtered)
            else:
                avg_score = sum(s["final_score"] for s in score_list) / len(score_list) if score_list else 0.0
            
            result.append({
                "miner_hotkey": miner_hotkey,
                "scores": score_list,
                "average_score": avg_score,
                "ema_score": self.calculate_ema_score(miner_hotkey, workflow_id),
                "validator_count": len(score_list)
            })
        
        return result
    
    def get_miner_history_scores(self, miner_hotkey: str, limit: int = 100) -> List[Dict]:
        scores = self.db.query(Score).filter(
            Score.miner_hotkey == miner_hotkey
        ).order_by(Score.created_at.desc()).limit(limit).all()
        
        return [
            {
                "workflow_id": s.workflow_id,
                "validator_hotkey": s.validator_hotkey,
                "final_score": s.final_score,
                "created_at": s.created_at.isoformat()
            }
            for s in scores
        ]
