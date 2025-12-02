from typing import Dict, Any, Optional
from kokoro.common.utils.logging import setup_logger
from kokoro.common.config.yaml_config import YamlConfig
from kokoro.common.models.workflow_type import WorkflowType
from kokoro.miner.services.text_training_service import TextTrainingService
from kokoro.miner.services.image_training_service import ImageTrainingService

logger = setup_logger(__name__)


class TrainingService:
    
    def __init__(self, config: Optional[YamlConfig] = None):
        self.config = config
        self.text_training_service = TextTrainingService(config)
        self.image_training_service = ImageTrainingService(config)
    
    async def train(self, task: Dict[str, Any]) -> Dict[str, Any]:
        workflow_type = task.get("workflow_type", "")
        
        try:
            workflow_type_enum = WorkflowType(workflow_type)
        except ValueError:
            raise ValueError(f"Unknown workflow type: {workflow_type}")
        
        if workflow_type_enum == WorkflowType.TEXT_LORA_CREATION:
            return await self.text_training_service.train_lora(task)
        elif workflow_type_enum == WorkflowType.IMAGE_LORA_CREATION:
            return await self.image_training_service.train_lora(task)
        else:
            raise ValueError(f"Unsupported workflow type: {workflow_type}")
    
    async def train_text_lora(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return await self.train(task)
    
    async def train_image_lora(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return await self.train(task)
