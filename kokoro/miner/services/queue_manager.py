import asyncio
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from kokoro.common.utils.logging import setup_logger
from kokoro.miner.services.training_service import TrainingService
from kokoro.miner.services.gpu_manager import GPUManager

logger = setup_logger(__name__)


class TaskPriority(Enum):
    HIGH = 3
    MEDIUM = 2
    LOW = 1


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class QueuedTask:
    def __init__(self, task_id: str, priority: TaskPriority, task_type: str, task_data: Dict[str, Any]):
        self.task_id = task_id
        self.priority = priority
        self.task_type = task_type
        self.task_data = task_data
        self.status = TaskStatus.PENDING
        self.enqueued_at = datetime.now(timezone.utc)
        self.started_at = None
        self.completed_at = None
        self.result = None
        self.error = None


class QueueManager:
    def __init__(self, max_queue_size: int = 100, max_training_jobs: int = 2, max_test_jobs: int = 4):
        self.high_priority_queue = asyncio.Queue()
        self.medium_priority_queue = asyncio.Queue()
        self.low_priority_queue = asyncio.Queue()
        self.running_tasks: Dict[str, QueuedTask] = {}
        self.completed_tasks: Dict[str, QueuedTask] = {}
        self.max_queue_size = max_queue_size
        self.max_training_jobs = max_training_jobs
        self.max_test_jobs = max_test_jobs
        self.scheduler_running = False
        self.training_service = None
        self.gpu_manager = None
    
    async def enqueue_task(self, task_data: Dict[str, Any]):
        task_id = task_data.get("workflow_id")
        workflow_type = task_data.get("workflow_type", "")
        
        if self.get_total_queue_size() >= self.max_queue_size:
            raise Exception("Task queue is full")
        
        from kokoro.common.models.workflow_type import WorkflowType
        
        try:
            workflow_type_enum = WorkflowType(workflow_type)
            if workflow_type_enum == WorkflowType.TEXT_LORA_CREATION:
                task_type = "text_lora_training"
                priority = TaskPriority.MEDIUM
            elif workflow_type_enum == WorkflowType.IMAGE_LORA_CREATION:
                task_type = "image_lora_training"
                priority = TaskPriority.MEDIUM
            else:
                task_type = "unknown"
                priority = TaskPriority.LOW
        except ValueError:
            logger.warning(f"Unknown workflow type: {workflow_type}, using LOW priority")
            task_type = "unknown"
            priority = TaskPriority.LOW
        
        queue_task = QueuedTask(task_id, priority, task_type, task_data)
        
        if priority == TaskPriority.HIGH:
            await self.high_priority_queue.put(queue_task)
        elif priority == TaskPriority.MEDIUM:
            await self.medium_priority_queue.put(queue_task)
        else:
            await self.low_priority_queue.put(queue_task)
        
        logger.info(f"Task {task_id} enqueued with priority {priority}")
    
    def get_total_queue_size(self) -> int:
        return (
            self.high_priority_queue.qsize() +
            self.medium_priority_queue.qsize() +
            self.low_priority_queue.qsize()
        )
    
    def get_queue_length(self) -> int:
        return self.get_total_queue_size()
    
    def get_running_tasks_count(self) -> int:
        return len(self.running_tasks)
    
    async def start_scheduler(self):
        if self.scheduler_running:
            logger.warning("Scheduler is already running")
            return
        
        self.scheduler_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Queue scheduler started")
    
    async def stop_scheduler(self):
        if not self.scheduler_running:
            return
        
        self.scheduler_running = False
        
        if hasattr(self, '_scheduler_task') and self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Queue scheduler stopped")
    
    async def _scheduler_loop(self):
        while self.scheduler_running:
            try:
                await self._process_queue()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _process_queue(self):
        if self.gpu_manager is None:
            from kokoro.miner.services.gpu_manager import GPUManager
            self.gpu_manager = GPUManager()
        
        if self.training_service is None:
            from kokoro.miner.services.training_service import TrainingService
            self.training_service = TrainingService()
        
        available_training_workers = self.gpu_manager.get_available_gpu_count()
        
        if available_training_workers == 0:
            return
        
        task = None
        
        if not self.high_priority_queue.empty():
            task = await self.high_priority_queue.get()
        elif not self.medium_priority_queue.empty():
            task = await self.medium_priority_queue.get()
        elif not self.low_priority_queue.empty():
            task = await self.low_priority_queue.get()
        
        if task is None:
            return
        
        if task.task_type in ["text_lora_training", "image_lora_training"]:
            training_count = len([
                t for t in self.running_tasks.values() 
                if t.task_type in ["text_lora_training", "image_lora_training"]
            ])
            if training_count >= self.max_training_jobs:
                await self._put_back(task)
                return
        
        gpu_id = self.gpu_manager.allocate_gpu(task.task_type)
        if gpu_id is None:
            await self._put_back(task)
            return
        
        asyncio.create_task(self._execute_task(task, gpu_id))
    
    async def _put_back(self, task: QueuedTask):
        if task.priority == TaskPriority.HIGH:
            await self.high_priority_queue.put(task)
        elif task.priority == TaskPriority.MEDIUM:
            await self.medium_priority_queue.put(task)
        else:
            await self.low_priority_queue.put(task)
    
    async def _execute_task(self, task: QueuedTask, gpu_id: int):
        """
        执行任务
        
        根据文档389-409行：
        1. 训练
        2. 本地测试（验证模型质量）
        3. 提交结果到任务中心
        """
        try:
            task.status = TaskStatus.PROCESSING
            task.started_at = datetime.now(timezone.utc)
            self.running_tasks[task.task_id] = task
            
            from kokoro.common.models.workflow_type import WorkflowType
            
            workflow_type = task.task_data.get("workflow_type", "")
            try:
                workflow_type_enum = WorkflowType(workflow_type)
                
                logger.info(f"Starting training for task {task.task_id}")
                result = await self.training_service.train(task.task_data)
                
                logger.info(f"Starting local testing for task {task.task_id}")
                test_result = await self._test_model_locally(result, workflow_type)
                result["local_test"] = test_result
                
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                task.result = result
                
                logger.info(f"Task {task.task_id} completed: training and local testing done")
                
            except ValueError:
                raise ValueError(f"Unknown workflow type: {workflow_type}")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(timezone.utc)
            task.error = str(e)
            logger.error(f"Task {task.task_id} failed: {e}")
        
        finally:
            self.gpu_manager.release_gpu(gpu_id)
            self.running_tasks.pop(task.task_id, None)
            self.completed_tasks[task.task_id] = task
    
    async def _test_model_locally(self, training_result: Dict[str, Any], workflow_type: str) -> Dict[str, Any]:
        try:
            from kokoro.miner.services.inference_service import InferenceService
            from kokoro.miner.schemas.inference import InferenceTestRequest, TestCase
            
            inference_service = InferenceService()
            model_url = training_result.get("model_url", training_result.get("model_path", ""))
            
            test_cases = [
                TestCase(
                    prompt="Test prompt for local validation",
                    seed=42,
                    inference_steps=30,
                    guidance_scale=7.0
                )
            ]
            
            test_request = InferenceTestRequest(
                model_url=model_url,
                test_cases=test_cases
            )
            
            test_results = await inference_service.test_lora(test_request, workflow_type)
            
            return {
                "test_passed": all(r.get("test_passed", False) for r in test_results),
                "test_results": test_results
            }
        except Exception as e:
            logger.error(f"Local testing failed: {e}", exc_info=True)
            return {
                "test_passed": False,
                "error": str(e)
            }
    
    def get_queue_stats(self) -> Dict[str, Any]:
        return {
            "high_priority_queue_length": self.high_priority_queue.qsize(),
            "medium_priority_queue_length": self.medium_priority_queue.qsize(),
            "low_priority_queue_length": self.low_priority_queue.qsize(),
            "total_queue_length": self.get_total_queue_size(),
            "running_training_tasks": len([t for t in self.running_tasks.values() if t.task_type in ["text_lora_training", "image_lora_training"]]),
            "running_inference_tasks": len([t for t in self.running_tasks.values() if t.task_type == "inference"]),
            "available_workers": self.gpu_manager.get_available_gpu_count(),
            "gpu_utilization": self.gpu_manager.get_gpu_utilization()
        }

