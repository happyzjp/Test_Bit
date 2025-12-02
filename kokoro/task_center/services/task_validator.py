from typing import Dict, Any, List, Tuple
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class TaskValidationError(Exception):
    """Raised when task validation fails"""
    pass


class TaskValidator:
    """Validates task configuration according to system architecture requirements"""
    
    @staticmethod
    def validate_workflow_spec(workflow_spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate workflow spec according to architecture document requirements.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # Validate required fields
        required_fields = ['theme', 'target_platform', 'deployment_target', 'training_mode', 'dataset_spec', 'training_spec']
        for field in required_fields:
            if field not in workflow_spec:
                errors.append(f"Missing required field: {field}")
        
        if errors:
            return False, errors
        
        # Validate training_mode
        training_mode = workflow_spec.get('training_mode')
        if training_mode not in ['new', 'incremental']:
            errors.append(f"Invalid training_mode: {training_mode}. Must be 'new' or 'incremental'")
        
        # Validate base_lora_url for incremental training
        if training_mode == 'incremental':
            base_lora_url = workflow_spec.get('base_lora_url')
            if not base_lora_url:
                errors.append("base_lora_url is required for incremental training")
            elif not isinstance(base_lora_url, str) or not base_lora_url.startswith(('http://', 'https://')):
                errors.append("base_lora_url must be a valid HTTP/HTTPS URL")
        
        # Validate training_spec
        training_spec = workflow_spec.get('training_spec', {})
        training_errors = TaskValidator._validate_training_spec(training_spec, workflow_spec.get('target_platform'))
        errors.extend(training_errors)
        
        # Validate dataset_spec
        dataset_spec = workflow_spec.get('dataset_spec', {})
        dataset_errors = TaskValidator._validate_dataset_spec(dataset_spec, workflow_spec.get('target_platform'))
        errors.extend(dataset_errors)
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _validate_training_spec(training_spec: Dict[str, Any], target_platform: str) -> List[str]:
        """Validate training_spec parameters"""
        errors = []
        
        # Required fields
        required_fields = ['base_model', 'lora_rank', 'lora_alpha', 'iteration_count', 'batch_size']
        for field in required_fields:
            if field not in training_spec:
                errors.append(f"Missing required training_spec field: {field}")
        
        if errors:
            return errors
        
        # Validate base_model
        base_model = training_spec.get('base_model')
        if not isinstance(base_model, str) or not base_model:
            errors.append("base_model must be a non-empty string")
        
        # Validate lora_rank
        lora_rank = training_spec.get('lora_rank')
        if not isinstance(lora_rank, int) or lora_rank < 1 or lora_rank > 128:
            errors.append("lora_rank must be an integer between 1 and 128")
        
        # Validate lora_alpha
        lora_alpha = training_spec.get('lora_alpha')
        if not isinstance(lora_alpha, int) or lora_alpha < 1 or lora_alpha > 256:
            errors.append("lora_alpha must be an integer between 1 and 256")
        
        # Validate iteration_count
        iteration_count = training_spec.get('iteration_count')
        if not isinstance(iteration_count, int) or iteration_count < 100 or iteration_count > 10000:
            errors.append("iteration_count must be an integer between 100 and 10000")
        
        # Validate batch_size
        batch_size = training_spec.get('batch_size')
        if not isinstance(batch_size, int) or batch_size < 1:
            errors.append("batch_size must be a positive integer")
        
        # Validate batch_size based on platform
        if target_platform == 'mobile':
            # Text LoRA: batch_size typically 1-8
            if batch_size > 8:
                errors.append("batch_size for mobile (text) tasks should not exceed 8")
        elif target_platform == 'executor':
            # Image LoRA: batch_size typically 1-2 (due to GPU memory)
            if batch_size > 2:
                errors.append("batch_size for executor (image) tasks should not exceed 2")
        
        # Validate learning_rate (optional but recommended)
        learning_rate = training_spec.get('learning_rate')
        if learning_rate is not None:
            if not isinstance(learning_rate, (int, float)) or learning_rate <= 0 or learning_rate > 0.01:
                errors.append("learning_rate must be a positive number between 0 and 0.01")
        
        # Validate resolution for image tasks
        if target_platform == 'executor':
            resolution = training_spec.get('resolution')
            if resolution is not None:
                if not isinstance(resolution, list) or len(resolution) != 2:
                    errors.append("resolution must be a list of two integers [width, height]")
                else:
                    width, height = resolution[0], resolution[1]
                    if not isinstance(width, int) or not isinstance(height, int):
                        errors.append("resolution width and height must be integers")
                    elif width < 256 or width > 1024 or height < 256 or height > 1024:
                        errors.append("resolution dimensions must be between 256 and 1024")
        
        return errors
    
    @staticmethod
    def _validate_dataset_spec(dataset_spec: Dict[str, Any], target_platform: str) -> List[str]:
        """Validate dataset_spec parameters"""
        errors = []
        
        # Required fields
        required_fields = ['source', 'repository_id']
        for field in required_fields:
            if field not in dataset_spec:
                errors.append(f"Missing required dataset_spec field: {field}")
        
        if errors:
            return errors
        
        # Validate source
        source = dataset_spec.get('source')
        if source != 'huggingface':
            errors.append("dataset source must be 'huggingface'")
        
        # Validate repository_id
        repository_id = dataset_spec.get('repository_id')
        if not isinstance(repository_id, str) or not repository_id:
            errors.append("repository_id must be a non-empty string")
        
        # Validate format-specific fields
        if target_platform == 'mobile':
            # Text LoRA: should have data_format, question_column, answer_column
            data_format = dataset_spec.get('data_format')
            if data_format != 'jsonl':
                errors.append("data_format for text tasks must be 'jsonl'")
            
            if 'question_column' not in dataset_spec or 'answer_column' not in dataset_spec:
                errors.append("text tasks require question_column and answer_column in dataset_spec")
        
        elif target_platform == 'executor':
            # Image LoRA: should have image_column, caption_column
            if 'image_column' not in dataset_spec or 'caption_column' not in dataset_spec:
                errors.append("image tasks require image_column and caption_column in dataset_spec")
        
        # Validate sample_count (optional but recommended)
        sample_count = dataset_spec.get('sample_count')
        if sample_count is not None:
            if not isinstance(sample_count, int) or sample_count < 1:
                errors.append("sample_count must be a positive integer")
        
        return errors
    
    @staticmethod
    def validate_task_create(task_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate complete task creation request.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # Validate workflow_id
        workflow_id = task_data.get('workflow_id')
        if not workflow_id or not isinstance(workflow_id, str):
            errors.append("workflow_id is required and must be a string")
        
        # Validate workflow_type
        workflow_type = task_data.get('workflow_type')
        if workflow_type not in ['text_lora_creation', 'image_lora_creation']:
            errors.append(f"Invalid workflow_type: {workflow_type}. Must be 'text_lora_creation' or 'image_lora_creation'")
        
        # Validate workflow_spec
        workflow_spec = task_data.get('workflow_spec')
        if not workflow_spec:
            errors.append("workflow_spec is required")
        else:
            spec_valid, spec_errors = TaskValidator.validate_workflow_spec(workflow_spec)
            if not spec_valid:
                errors.extend(spec_errors)
        
        # Validate durations
        for duration_field in ['announcement_duration', 'execution_duration', 'review_duration']:
            duration = task_data.get(duration_field)
            if duration is not None:
                if not isinstance(duration, (int, float)) or duration < 0:
                    errors.append(f"{duration_field} must be a non-negative number")
        
        return len(errors) == 0, errors

