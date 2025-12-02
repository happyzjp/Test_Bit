#!/usr/bin/env python3
import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from kokoro.website_admin.schemas.task import TaskPublishRequest, WorkflowSpec, DatasetSpec, TrainingSpec
from kokoro.common.models.workflow_type import WorkflowType
import httpx
import yaml


def load_config():
    config_path = os.getenv("WEBSITE_ADMIN_CONFIG", "config.yml")
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def create_text_lora_task(
    workflow_id: str,
    theme: str = "japanese_culture_chat",
    training_mode: str = "new",
    base_lora_url: str = None,
    dataset_repo: str = "kokoro/japanese-culture-qa-dataset",
    sample_count: int = 2000,
    base_model: str = "Qwen/Qwen3-0.6B",
    announcement_duration: float = 0.25,
    execution_duration: float = 3.0,
    review_duration: float = 1.0,
    reward_duration: float = 0.0
):
    dataset_spec = DatasetSpec(
        source="huggingface",
        repository_id=dataset_repo,
        sample_count=sample_count,
        data_format="jsonl",
        question_column="question",
        answer_column="answer"
    )
    
    training_spec = TrainingSpec(
        base_model=base_model,
        lora_rank=16,
        lora_alpha=32,
        iteration_count=1000,
        batch_size=4,
        learning_rate=2e-4,
        max_length=512
    )
    
    workflow_spec = WorkflowSpec(
        theme=theme,
        target_platform="mobile",
        deployment_target="mobile_app",
        training_mode=training_mode,
        dataset_spec=dataset_spec,
        training_spec=training_spec,
        base_lora_url=base_lora_url
    )
    
    return TaskPublishRequest(
        workflow_id=workflow_id,
        workflow_type=WorkflowType.TEXT_LORA_CREATION.value,
        workflow_spec=workflow_spec,
        announcement_duration=announcement_duration,
        execution_duration=execution_duration,
        review_duration=review_duration,
        reward_duration=reward_duration
    )


def create_image_lora_task(
    workflow_id: str,
    theme: str = "manga_style",
    training_mode: str = "new",
    base_lora_url: str = None,
    dataset_repo: str = "kokoro/manga-style-dataset",
    sample_count: int = 200,
    base_model: str = "black-forest-labs/FLUX.1-dev",
    announcement_duration: float = 0.25,
    execution_duration: float = 3.0,
    review_duration: float = 1.0,
    reward_duration: float = 0.0
):
    dataset_spec = DatasetSpec(
        source="huggingface",
        repository_id=dataset_repo,
        sample_count=sample_count,
        image_column="image",
        caption_column="text"
    )
    
    training_spec = TrainingSpec(
        base_model=base_model,
        lora_rank=16,
        lora_alpha=32,
        iteration_count=1000,
        batch_size=2,
        learning_rate=1e-4,
        resolution=[512, 768]
    )
    
    workflow_spec = WorkflowSpec(
        theme=theme,
        target_platform="executor",
        deployment_target="executor_node",
        training_mode=training_mode,
        dataset_spec=dataset_spec,
        training_spec=training_spec,
        base_lora_url=base_lora_url
    )
    
    return TaskPublishRequest(
        workflow_id=workflow_id,
        workflow_type=WorkflowType.IMAGE_LORA_CREATION.value,
        workflow_spec=workflow_spec,
        announcement_duration=announcement_duration,
        execution_duration=execution_duration,
        review_duration=review_duration,
        reward_duration=reward_duration
    )


def publish_task(task_request: TaskPublishRequest, config: dict):
    task_center_url = config.get('task_center', {}).get('url', 'http://localhost:8000')
    api_key = config.get('api', {}).get('key')
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{task_center_url}/v1/tasks/publish",
                json=task_request.dict(),
                headers=headers
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        print(f"Error: {e.response.status_code} - {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"HTTP Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Create KOKORO tasks')
    parser.add_argument('--type', choices=['text', 'image'], required=True,
                       help='Task type: text or image')
    parser.add_argument('--workflow-id', required=True,
                       help='Workflow ID (e.g., wf_20240101_001)')
    parser.add_argument('--theme', default=None,
                       help='Theme (default: japanese_culture_chat for text, manga_style for image)')
    parser.add_argument('--training-mode', choices=['new', 'incremental'], default='new',
                       help='Training mode: new or incremental')
    parser.add_argument('--base-lora-url', default=None,
                       help='Base LoRA URL for incremental training')
    parser.add_argument('--dataset-repo', default=None,
                       help='Dataset repository ID')
    parser.add_argument('--sample-count', type=int, default=None,
                       help='Sample count')
    parser.add_argument('--base-model', default=None,
                       help='Base model name')
    parser.add_argument('--announcement-duration', type=float, default=0.25,
                       help='Announcement duration in days (default: 0.25)')
    parser.add_argument('--execution-duration', type=float, default=3.0,
                       help='Execution duration in days (default: 3.0)')
    parser.add_argument('--review-duration', type=float, default=1.0,
                       help='Review duration in days (default: 1.0)')
    parser.add_argument('--reward-duration', type=float, default=0.0,
                       help='Reward duration in days (default: 0.0)')
    parser.add_argument('--config', default=None,
                       help='Config file path (default: config.yml)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Print task JSON without publishing')
    
    args = parser.parse_args()
    
    if args.config:
        os.environ['WEBSITE_ADMIN_CONFIG'] = args.config
    
    config = load_config()
    
    if args.type == 'text':
        theme = args.theme or "japanese_culture_chat"
        dataset_repo = args.dataset_repo or "kokoro/japanese-culture-qa-dataset"
        sample_count = args.sample_count or 2000
        base_model = args.base_model or "Qwen/Qwen3-0.6B"
        
        task_request = create_text_lora_task(
            workflow_id=args.workflow_id,
            theme=theme,
            training_mode=args.training_mode,
            base_lora_url=args.base_lora_url,
            dataset_repo=dataset_repo,
            sample_count=sample_count,
            base_model=base_model,
            announcement_duration=args.announcement_duration,
            execution_duration=args.execution_duration,
            review_duration=args.review_duration,
            reward_duration=args.reward_duration
        )
    else:
        theme = args.theme or "manga_style"
        dataset_repo = args.dataset_repo or "kokoro/manga-style-dataset"
        sample_count = args.sample_count or 200
        base_model = args.base_model or "black-forest-labs/FLUX.1-dev"
        
        task_request = create_image_lora_task(
            workflow_id=args.workflow_id,
            theme=theme,
            training_mode=args.training_mode,
            base_lora_url=args.base_lora_url,
            dataset_repo=dataset_repo,
            sample_count=sample_count,
            base_model=base_model,
            announcement_duration=args.announcement_duration,
            execution_duration=args.execution_duration,
            review_duration=args.review_duration,
            reward_duration=args.reward_duration
        )
    
    if args.dry_run:
        print(json.dumps(task_request.dict(), indent=2, default=str))
    else:
        result = publish_task(task_request, config)
        print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()

