from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional, Dict, Any
from kokoro.common.models.audit_task import AuditTask
from kokoro.common.models.task import Task
from kokoro.common.models.validator import Validator
from kokoro.common.utils.logging import setup_logger
from kokoro.task_center import shared
from datetime import datetime, timezone
import uuid
import random

logger = setup_logger(__name__)


class AuditTaskCreator:
    def __init__(self, db: Session):
        self.db = db
        self.bittensor_client = shared.bittensor_client
        self.validators_per_task = 3
    
    def create_audit_task(
        self,
        workflow_id: str,
        miner_hotkey: str,
        lora_url: str
    ) -> AuditTask:
        task = self.db.query(Task).filter(Task.workflow_id == workflow_id).first()
        if not task:
            raise ValueError("Task not found")
        
        audit_task_id = f"audit_{uuid.uuid4().hex[:12]}"
        
        task_info = {
            "prompt": task.workflow_spec.get("prompt", ""),
            "seed": task.workflow_spec.get("seed", 42),
            "base_model": task.workflow_spec.get("training_spec", {}).get("base_model", ""),
            "target_vector": task.workflow_spec.get("target_vector", [])
        }
        
        audit_task = AuditTask(
            audit_task_id=audit_task_id,
            original_task_id=workflow_id,
            miner_hotkey=miner_hotkey,
            lora_url=lora_url,
            task_info=task_info,
            is_completed=False
        )
        
        self.db.add(audit_task)
        self.db.commit()
        self.db.refresh(audit_task)
        
        logger.info(f"Audit task created: {audit_task_id} for miner {miner_hotkey}")
        
        return audit_task
    
    def assign_audit_task_to_validator(
        self,
        audit_task_id: str,
        validator_key: str
    ) -> Optional[AuditTask]:
        base_audit_task = self.db.query(AuditTask).filter(
            AuditTask.audit_task_id == audit_task_id
        ).first()
        
        if not base_audit_task:
            return None
        
        existing_assignment = self.db.query(AuditTask).filter(
            and_(
                AuditTask.original_task_id == base_audit_task.original_task_id,
                AuditTask.miner_hotkey == base_audit_task.miner_hotkey,
                AuditTask.validator_hotkey == validator_key
            )
        ).first()
        
        if existing_assignment:
            return None
        
        validator = self.db.query(Validator).filter(Validator.hotkey == validator_key).first()
        if not validator:
            stake = self.bittensor_client.get_validator_stake(validator_key)
            validator = Validator(hotkey=validator_key, stake=stake, reputation=0.0)
            self.db.add(validator)
            self.db.commit()
        
        new_audit_task = AuditTask(
            audit_task_id=f"{audit_task_id}_{validator_key}_{uuid.uuid4().hex[:8]}",
            original_task_id=base_audit_task.original_task_id,
            miner_hotkey=base_audit_task.miner_hotkey,
            validator_hotkey=validator_key,
            lora_url=base_audit_task.lora_url,
            task_info=base_audit_task.task_info,
            is_completed=False
        )
        
        self.db.add(new_audit_task)
        self.db.commit()
        self.db.refresh(new_audit_task)
        
        return new_audit_task
    
    def auto_assign_audit_tasks(self, workflow_id: str):
        audit_tasks = self.db.query(AuditTask).filter(
            and_(
                AuditTask.original_task_id == workflow_id,
                AuditTask.validator_hotkey.is_(None)
            )
        ).all()
        
        if not audit_tasks:
            return
        
        all_validators_data = self.bittensor_client.get_all_miners()
        eligible_validators = []
        
        for v_data in all_validators_data:
            if not v_data.get("is_active", False):
                continue
            
            validator = self.db.query(Validator).filter(
                Validator.hotkey == v_data["hotkey"]
            ).first()
            
            if not validator:
                validator = Validator(
                    hotkey=v_data["hotkey"],
                    stake=v_data.get("stake", 0.0),
                    reputation=0.0
                )
                self.db.add(validator)
                self.db.commit()
            
            pending_count = self.db.query(AuditTask).filter(
                and_(
                    AuditTask.validator_hotkey == v_data["hotkey"],
                    AuditTask.is_completed == False
                )
            ).count()
            
            priority_score = validator.reputation * 0.7 - pending_count * 0.3
            
            eligible_validators.append({
                "hotkey": v_data["hotkey"],
                "stake": v_data.get("stake", 0.0),
                "reputation": validator.reputation,
                "pending_count": pending_count,
                "priority_score": priority_score
            })
        
        if not eligible_validators:
            logger.warning(f"No eligible validators found for workflow {workflow_id}")
            return
        
        eligible_validators.sort(key=lambda x: x["priority_score"], reverse=True)
        
        validator_assignment_count = {v["hotkey"]: 0 for v in eligible_validators}
        
        for audit_task in audit_tasks:
            assigned_count = self.db.query(AuditTask).filter(
                and_(
                    AuditTask.original_task_id == audit_task.original_task_id,
                    AuditTask.miner_hotkey == audit_task.miner_hotkey,
                    AuditTask.validator_hotkey.isnot(None)
                )
            ).count()
            
            if assigned_count >= self.validators_per_task:
                continue
            
            needed = self.validators_per_task - assigned_count
            
            candidates = sorted(
                eligible_validators,
                key=lambda x: (
                    x["priority_score"],
                    -validator_assignment_count[x["hotkey"]],
                    x["pending_count"]
                ),
                reverse=True
            )
            
            selected_validators = candidates[:needed]
            
            for validator in selected_validators:
                assigned = self.assign_audit_task_to_validator(
                    audit_task.audit_task_id,
                    validator["hotkey"]
                )
                
                if assigned:
                    validator_assignment_count[validator["hotkey"]] += 1
                    logger.info(
                        f"Assigned audit task {audit_task.audit_task_id} to validator "
                        f"{validator['hotkey']} (priority={validator['priority_score']:.2f}, "
                        f"load={validator['pending_count']})"
                    )
    
    def update_audit_task_status(
        self,
        audit_task_id: str,
        status: str,
        result: Optional[Dict] = None
    ):
        audit_task = self.db.query(AuditTask).filter(
            AuditTask.audit_task_id == audit_task_id
        ).first()
        
        if not audit_task:
            logger.warning(f"Audit task not found: {audit_task_id}")
            return
        
        audit_task.is_completed = (status == "completed")
        if result:
            audit_task.result = result
        
        if status == "completed":
            audit_task.completed_at = datetime.now(timezone.utc)
        
        self.db.commit()
        logger.info(f"Audit task {audit_task_id} status updated to {status}")
    
    def get_audit_task_status(self, workflow_id: str) -> Dict[str, Any]:
        audit_tasks = self.db.query(AuditTask).filter(
            AuditTask.original_task_id == workflow_id
        ).all()
        
        total = len(audit_tasks)
        completed = sum(1 for t in audit_tasks if t.is_completed)
        pending = total - completed
        
        return {
            "workflow_id": workflow_id,
            "total_audit_tasks": total,
            "completed": completed,
            "pending": pending,
            "completion_rate": completed / total if total > 0 else 0.0
        }
    
    def get_pending_tasks_for_validator(self, validator_key: str) -> List[AuditTask]:
        return self.db.query(AuditTask).filter(
            and_(
                AuditTask.validator_hotkey == validator_key,
                AuditTask.is_completed == False
            )
        ).all()

