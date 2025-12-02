from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from kokoro.common.models.task import Task, TaskStatus
from kokoro.common.models.miner import Miner
from kokoro.task_center.schemas.task import TaskCreate
from kokoro.task_center.schemas.miner import MinerSubmitRequest
from kokoro.task_center.services.task_repository import TaskRepository
from kokoro.task_center.services.audit_task_creator import AuditTaskCreator
from kokoro.task_center.services.miner_selector import MinerSelector
from kokoro.task_center.services.miner_cache import MinerCache
from kokoro.common.bittensor.client import BittensorClient
from kokoro.common.utils.logging import setup_logger
import uuid
import asyncio

logger = setup_logger(__name__)


class TaskDispatcher:
    def __init__(self, db: Session, miner_cache: MinerCache):
        self.db = db
        self.repository = TaskRepository(db)
        self.audit_creator = AuditTaskCreator(db)
        self.miner_selector = MinerSelector(db, miner_cache)
        self.bittensor_client = BittensorClient("task_center", "default")
    
    def create_task(self, task_data: TaskCreate) -> Task:
        now = datetime.now(timezone.utc)
        
        # According to architecture doc: announcement_duration is in days (typically 0.25 = 6 hours)
        # execution_duration is in days (typically 3.0 = 72 hours)
        # review_duration is in days (typically 1.0 = 24 hours)
        announcement_duration = task_data.announcement_duration
        execution_duration = task_data.execution_duration
        review_duration = task_data.review_duration
        reward_duration = getattr(task_data, 'reward_duration', 0.0)
        
        announcement_start = now
        execution_start = announcement_start + timedelta(days=announcement_duration)
        review_start = execution_start + timedelta(days=execution_duration)
        reward_start = review_start + timedelta(days=review_duration)
        workflow_end = reward_start + timedelta(days=reward_duration)
        
        # Determine initial status based on publish_status
        initial_status = TaskStatus.ANNOUNCEMENT
        if hasattr(task_data, 'publish_status') and task_data.publish_status == 'draft':
            initial_status = TaskStatus.PENDING
        
        task = Task(
            task_id=getattr(task_data, 'task_id', None),
            workflow_id=task_data.workflow_id,
            workflow_type=task_data.workflow_type,
            workflow_spec=task_data.workflow_spec.dict(),
            status=initial_status,
            publish_status=getattr(task_data, 'publish_status', 'draft'),
            start_date=getattr(task_data, 'start_date', None),
            end_date=getattr(task_data, 'end_date', None),
            description=getattr(task_data, 'description', None),
            hf_dataset_url=getattr(task_data, 'hf_dataset_url', None),
            pdf_file_url=getattr(task_data, 'pdf_file_url', None),
            announcement_start=announcement_start if initial_status != TaskStatus.PENDING else None,
            execution_start=execution_start if initial_status != TaskStatus.PENDING else None,
            review_start=review_start if initial_status != TaskStatus.PENDING else None,
            reward_start=reward_start if initial_status != TaskStatus.PENDING else None,
            workflow_end=workflow_end if initial_status != TaskStatus.PENDING else None
        )
        
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        
        logger.info(f"Task created: {task.workflow_id}")
        
        asyncio.create_task(self._assign_task_to_miners(task))
        
        return task
    
    async def _assign_task_to_miners(self, task: Task):
        selected_miners = self.miner_selector.select_miners(task.workflow_id, count=10)
        
        if not selected_miners:
            logger.warning(f"No eligible miners found for task {task.workflow_id}")
            return
        
        task_data = {
            "workflow_id": task.workflow_id,
            "workflow_type": task.workflow_type,
            "workflow_spec": task.workflow_spec,
            "announcement_start": task.announcement_start.isoformat() if task.announcement_start else None,
            "execution_start": task.execution_start.isoformat() if task.execution_start else None,
            "review_start": task.review_start.isoformat() if task.review_start else None,
            "reward_start": task.reward_start.isoformat() if task.reward_start else None,
            "workflow_end": task.workflow_end.isoformat() if task.workflow_end else None
        }
        
        results = await self.miner_selector.assign_task_to_miners(
            task.workflow_id,
            task_data,
            selected_miners
        )
        
        success_count = sum(1 for v in results.values() if v)
        logger.info(f"Task {task.workflow_id} assigned to {success_count}/{len(selected_miners)} miners")
    
    def assign_task_to_miner(self, workflow_id: str, miner_key: str) -> Task:
        task = self.repository.get_by_workflow_id(workflow_id)
        if not task:
            return None
        
        stake = self.bittensor_client.get_miner_stake(miner_key)
        
        if stake < 1000.0:
            logger.warning(f"Miner {miner_key} stake too low: {stake}")
            return None
        
        miner = self.db.query(Miner).filter(Miner.hotkey == miner_key).first()
        if not miner:
            miner = Miner(hotkey=miner_key, stake=stake, reputation=0.0)
            self.db.add(miner)
        else:
            miner.stake = stake
            self.db.commit()
        
        return task
    
    def select_miners_for_task(self, workflow_id: str, count: int = 10) -> list:
        return self.miner_selector.select_miners(workflow_id, count)
    
    def receive_miner_submission(self, request: MinerSubmitRequest) -> dict:
        task = self.repository.get_by_workflow_id(request.workflow_id)
        if not task:
            raise ValueError("Task not found")
        
        submission_id = str(uuid.uuid4())
        
        from kokoro.common.models.miner_submission import MinerSubmission
        
        submission = MinerSubmission(
            id=submission_id,
            workflow_id=request.workflow_id,
            miner_hotkey=request.miner_key,
            model_url=request.model_url,
            sample_images=request.sample_images,
            submission_data=request.dict(),
            status="pending_verification"
        )
        
        self.db.add(submission)
        self.db.commit()
        
        logger.info(f"Miner submission stored: {submission_id} for workflow {request.workflow_id}")
        
        audit_task = self.audit_creator.create_audit_task(
            workflow_id=request.workflow_id,
            miner_hotkey=request.miner_key,
            lora_url=request.model_url
        )
        
        self.audit_creator.auto_assign_audit_tasks(request.workflow_id)
        
        asyncio.create_task(self._notify_validators(audit_task.audit_task_id))
        
        return {
            "submission_id": submission_id,
            "workflow_id": request.workflow_id,
            "status": "pending_verification",
            "estimated_reward": 0.0
        }
    
    async def _notify_validators(self, audit_task_id: str):
        from kokoro.common.models.audit_task import AuditTask
        
        audit_tasks = self.db.query(AuditTask).filter(
            AuditTask.audit_task_id.like(f"{audit_task_id}%")
        ).all()
        
        for audit_task in audit_tasks:
            if not audit_task.validator_hotkey:
                continue
            
            try:
                import httpx
                validator_url = f"http://{audit_task.validator_hotkey}:8000"
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{validator_url}/v1/audit/receive",
                        json={
                            "audit_task_id": audit_task.audit_task_id,
                            "validator_key": audit_task.validator_hotkey
                        }
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"Notified validator {audit_task.validator_hotkey} about audit task {audit_task.audit_task_id}")
            except Exception as e:
                logger.error(f"Failed to notify validator {audit_task.validator_hotkey}: {e}")

