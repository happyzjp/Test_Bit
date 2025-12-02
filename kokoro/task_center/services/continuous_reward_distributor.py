from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Dict, List, Optional
from kokoro.common.models.reward_distribution import RewardDistribution
from kokoro.common.models.task import Task, TaskStatus
from kokoro.common.models.audit_task import AuditTask
from kokoro.common.models.score import Score
from kokoro.common.services.reward import RewardService
from kokoro.common.services.scoring import ScoringService
from kokoro.common.bittensor.client import BittensorClient
from kokoro.task_center.services.task_lifecycle_manager import TaskLifecycleManager
from kokoro.task_center.services.score_archive import ScoreArchive
from kokoro.common.utils.logging import setup_logger
import uuid

logger = setup_logger(__name__)


class ContinuousRewardDistributor:
    
    def __init__(self, db: Session):
        self.db = db
        self.reward_service = RewardService()
        self.scoring_service = ScoringService()
        self.bittensor_client = BittensorClient("task_center", "default")
        self.lifecycle_manager = TaskLifecycleManager(db)
        self.score_archive = ScoreArchive(db)
    
    def distribute_rewards_for_completed_audit(
        self,
        audit_task_id: str,
        workflow_id: str
    ) -> Dict[str, float]:
        if not self.lifecycle_manager.is_task_in_execution_or_review(workflow_id):
            logger.warning(f"Task {workflow_id} is not in execution or review phase, skipping reward distribution")
            return {}
        
        if self.lifecycle_manager.is_task_ended(workflow_id):
            logger.warning(f"Task {workflow_id} has ended, skipping reward distribution")
            return {}
        
        audit_task = self.db.query(AuditTask).filter(
            AuditTask.audit_task_id == audit_task_id
        ).first()
        
        if not audit_task:
            logger.warning(f"Audit task {audit_task_id} not found")
            return {}
        
        task = self.db.query(Task).filter(Task.workflow_id == workflow_id).first()
        if not task:
            logger.warning(f"Task {workflow_id} not found")
            return {}
        
        miner_scores = self.score_archive.get_all_scores_for_workflow(workflow_id)
        
        eligible_miners = {}
        miner_submit_times = {}
        
        for miner_data in miner_scores:
            miner_hotkey = miner_data["miner_hotkey"]
            avg_score = miner_data.get("average_score", 0.0)
            
            if avg_score < 3.5:
                continue
            
            eligible_miners[miner_hotkey] = avg_score
            
            from kokoro.common.models.miner_submission import MinerSubmission
            submission = self.db.query(MinerSubmission).filter(
                MinerSubmission.workflow_id == workflow_id,
                MinerSubmission.miner_hotkey == miner_hotkey
            ).order_by(MinerSubmission.created_at.desc()).first()
            
            if submission:
                miner_submit_times[miner_hotkey] = submission.created_at
        
        if not eligible_miners:
            logger.info(f"No eligible miners for workflow {workflow_id} (all below baseline)")
            return {}
        
        miner_weights = {}
        miner_time_coefficients = {}
        for miner_hotkey, score in eligible_miners.items():
            quality_score = self.scoring_service.calculate_quality_score(score)
            
            time_coefficient = 1.0
            if miner_submit_times.get(miner_hotkey) and task.execution_start and task.review_start:
                submit_time = miner_submit_times[miner_hotkey]
                time_coefficient = self.scoring_service.calculate_time_coefficient(
                    submit_time, task.execution_start, task.review_start
                )
            
            miner_time_coefficients[miner_hotkey] = time_coefficient
            
            constraint_coefficient = 1.0
            
            final_weight = self.scoring_service.calculate_final_weight(
                quality_score,
                time_coefficient,
                constraint_coefficient
            )
            
            miner_weights[miner_hotkey] = final_weight
        
        total_emission = self.bittensor_client.get_emission()
        task_type = task.workflow_type.value if hasattr(task.workflow_type, 'value') else str(task.workflow_type)
        
        rewards = self.reward_service.calculate_rewards(
            miner_scores=eligible_miners,
            miner_weights=miner_weights,
            task_type=task_type,
            total_emission=total_emission
        )
        
        distribution_round = f"audit_{audit_task_id}"
        for miner_hotkey, reward_amount in rewards.items():
            if reward_amount > 0:
                distribution_id = str(uuid.uuid4())
                distribution = RewardDistribution(
                    id=distribution_id,
                    workflow_id=workflow_id,
                    miner_hotkey=miner_hotkey,
                    reward_amount=reward_amount,
                    weight=miner_weights.get(miner_hotkey, 0.0),
                    score=eligible_miners.get(miner_hotkey, 0.0),
                    distribution_data={
                        "audit_task_id": audit_task_id,
                        "time_coefficient": miner_time_coefficients.get(miner_hotkey, 1.0),
                        "quality_score": self.scoring_service.calculate_quality_score(
                            eligible_miners.get(miner_hotkey, 0.0)
                        )
                    },
                    distribution_round=distribution_round
                )
                self.db.add(distribution)
        
        self.db.commit()
        
        logger.info(
            f"Rewards distributed for workflow {workflow_id} (audit {audit_task_id}): "
            f"{len([r for r in rewards.values() if r > 0])} miners received rewards"
        )
        
        return rewards
    
    def get_total_rewards_for_miner(
        self,
        workflow_id: str,
        miner_hotkey: str
    ) -> float:
        distributions = self.db.query(RewardDistribution).filter(
            RewardDistribution.workflow_id == workflow_id,
            RewardDistribution.miner_hotkey == miner_hotkey
        ).all()
        
        return sum(d.reward_amount for d in distributions)
    
    def get_all_rewards_for_workflow(self, workflow_id: str) -> Dict[str, float]:
        distributions = self.db.query(RewardDistribution).filter(
            RewardDistribution.workflow_id == workflow_id
        ).all()
        
        miner_rewards = {}
        for dist in distributions:
            if dist.miner_hotkey not in miner_rewards:
                miner_rewards[dist.miner_hotkey] = 0.0
            miner_rewards[dist.miner_hotkey] += dist.reward_amount
        
        return miner_rewards
