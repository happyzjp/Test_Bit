from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from kokoro.common.models.task import Task, TaskStatus
from kokoro.common.utils.logging import setup_logger
import asyncio

logger = setup_logger(__name__)


class TaskLifecycleManager:
    
    def __init__(self, db: Session):
        self.db = db
        self.is_running = False
        self._lifecycle_task = None
    
    async def start(self):
        if self.is_running:
            logger.warning("Task lifecycle manager is already running")
            return
        
        self.is_running = True
        self._lifecycle_task = asyncio.create_task(self._lifecycle_loop())
        logger.info("Task lifecycle manager started")
    
    async def stop(self):
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self._lifecycle_task:
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Task lifecycle manager stopped")
    
    async def _lifecycle_loop(self):
        while self.is_running:
            try:
                await self._update_task_statuses()
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                logger.info("Lifecycle loop cancelled")
                break
            except Exception as e:
                logger.error(f"Task lifecycle loop error: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _update_task_statuses(self):
        from kokoro.common.database import SessionLocal
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            
            active_tasks = db.query(Task).filter(
                Task.status.in_([
                    TaskStatus.ANNOUNCEMENT,
                    TaskStatus.EXECUTION,
                    TaskStatus.REVIEW,
                    TaskStatus.REWARD
                ])
            ).all()
            
            for task in active_tasks:
                try:
                    if task.status == TaskStatus.ANNOUNCEMENT:
                        if task.execution_start and now >= task.execution_start:
                            task.status = TaskStatus.EXECUTION
                            logger.info(f"Task {task.workflow_id} entered EXECUTION phase")
                    
                    elif task.status == TaskStatus.EXECUTION:
                        if task.review_start and now >= task.review_start:
                            task.status = TaskStatus.REVIEW
                            logger.info(f"Task {task.workflow_id} entered REVIEW phase")
                    
                    elif task.status == TaskStatus.REVIEW:
                        if task.reward_start and now >= task.reward_start:
                            task.status = TaskStatus.REWARD
                            logger.info(f"Task {task.workflow_id} entered REWARD phase")
                    
                    elif task.status == TaskStatus.REWARD:
                        if task.workflow_end and now >= task.workflow_end:
                            task.status = TaskStatus.ENDED
                            logger.info(f"Task {task.workflow_id} ended")
                    
                    db.commit()
                except Exception as e:
                    logger.error(f"Error updating task {task.workflow_id} status: {e}", exc_info=True)
                    db.rollback()
        except Exception as e:
            logger.error(f"Error in update_task_statuses: {e}", exc_info=True)
        finally:
            db.close()
    
    def is_task_in_execution_or_review(self, workflow_id: str) -> bool:
        try:
            task = self.db.query(Task).filter(Task.workflow_id == workflow_id).first()
            if not task:
                return False
            
            return task.status in [TaskStatus.EXECUTION, TaskStatus.REVIEW]
        except Exception as e:
            logger.error(f"Error checking task status: {e}", exc_info=True)
            return False
    
    def is_task_ended(self, workflow_id: str) -> bool:
        try:
            task = self.db.query(Task).filter(Task.workflow_id == workflow_id).first()
            if not task:
                return False
            
            return task.status == TaskStatus.ENDED
        except Exception as e:
            logger.error(f"Error checking if task ended: {e}", exc_info=True)
            return False
