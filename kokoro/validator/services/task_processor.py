import asyncio
from typing import Dict, Any, Optional
from kokoro.validator.services.audit_validator import AuditValidator
from kokoro.validator.services.score_calculator import ScoreCalculator
from kokoro.common.utils.logging import setup_logger
import httpx
from kokoro.common.config import settings
from kokoro.common.bittensor.wallet import WalletManager

logger = setup_logger(__name__)


class TaskProcessor:
    def __init__(self, wallet_manager: WalletManager):
        self.wallet_manager = wallet_manager
        self.audit_validator = AuditValidator()
        self.score_calculator = ScoreCalculator()
        self.is_running = False
        self.process_interval = 60
        self._process_task = None
    
    async def start(self):
        if self.is_running:
            logger.warning("Task processor is already running")
            return
        
        self.is_running = True
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info("Task processor started")
    
    async def stop(self):
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Task processor stopped")
    
    async def _process_loop(self):
        while self.is_running:
            try:
                await self._process_pending_tasks()
                await asyncio.sleep(self.process_interval)
            except asyncio.CancelledError:
                logger.info("Process loop cancelled")
                break
            except Exception as e:
                logger.error(f"Task processing loop error: {e}", exc_info=True)
                await asyncio.sleep(self.process_interval)
    
    async def _process_pending_tasks(self):
        try:
            validator_key = self.wallet_manager.get_hotkey()
            task_center_url = settings.TASK_CENTER_URL
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{task_center_url}/v1/audit/pending",
                    params={"validator_key": validator_key}
                )
                
                if response.status_code == 200:
                    tasks = response.json()
                    for task in tasks:
                        try:
                            await self._process_audit_task(task)
                        except Exception as e:
                            logger.error(f"Failed to process audit task {task.get('id')}: {e}", exc_info=True)
                            continue
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching pending tasks: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error processing pending tasks: {e}", exc_info=True)
    
    async def _process_audit_task(self, task: Dict[str, Any]):
        try:
            result = await self.audit_validator.process_audit_task(task)
            score = self.score_calculator.calculate_score(result)
            
            task_center_url = settings.TASK_CENTER_URL
            async with httpx.AsyncClient(timeout=30.0) as client:
                await client.post(
                    f"{task_center_url}/v1/scores/submit",
                    json={
                        "workflow_id": task.get("workflow_id"),
                        "miner_hotkey": task.get("miner_hotkey"),
                        "validator_hotkey": self.wallet_manager.get_hotkey(),
                        "score": score
                    }
                )
        except Exception as e:
            logger.error(f"Failed to process audit task: {e}", exc_info=True)
            raise
