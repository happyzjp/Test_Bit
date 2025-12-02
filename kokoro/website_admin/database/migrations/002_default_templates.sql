INSERT INTO task_templates (name, description, workflow_type, workflow_spec, announcement_duration, execution_duration, review_duration, reward_duration, is_active)
VALUES 
(
    'text_lora_new_default',
    'Default template for new text LoRA training',
    'text_lora_creation',
    '{
        "theme": "japanese_culture_chat",
        "target_platform": "mobile",
        "deployment_target": "mobile_app",
        "training_mode": "new",
        "dataset_spec": {
            "source": "huggingface",
            "repository_id": "kokoro/japanese-culture-qa-dataset",
            "sample_count": 2000,
            "data_format": "jsonl",
            "question_column": "question",
            "answer_column": "answer"
        },
        "training_spec": {
            "base_model": "Qwen/Qwen3-0.6B",
            "lora_rank": 16,
            "lora_alpha": 32,
            "iteration_count": 1000,
            "batch_size": 4,
            "learning_rate": 0.0002,
            "max_length": 512
        }
    }'::jsonb,
    '0.25',
    '3.0',
    '1.0',
    '0.0',
    TRUE
),
(
    'text_lora_incremental_default',
    'Default template for incremental text LoRA training',
    'text_lora_creation',
    '{
        "theme": "japanese_culture_chat",
        "target_platform": "mobile",
        "deployment_target": "mobile_app",
        "training_mode": "incremental",
        "dataset_spec": {
            "source": "huggingface",
            "repository_id": "kokoro/japanese-culture-qa-dataset-v2",
            "sample_count": 1500,
            "data_format": "jsonl",
            "question_column": "question",
            "answer_column": "answer"
        },
        "training_spec": {
            "base_model": "Qwen/Qwen3-0.6B",
            "lora_rank": 16,
            "lora_alpha": 32,
            "iteration_count": 800,
            "batch_size": 4,
            "learning_rate": 0.0001,
            "max_length": 512
        }
    }'::jsonb,
    '0.25',
    '3.0',
    '1.0',
    '0.0',
    TRUE
),
(
    'image_lora_new_default',
    'Default template for new image LoRA training',
    'image_lora_creation',
    '{
        "theme": "manga_style",
        "target_platform": "executor",
        "deployment_target": "executor_node",
        "training_mode": "new",
        "dataset_spec": {
            "source": "huggingface",
            "repository_id": "kokoro/manga-style-dataset",
            "sample_count": 200,
            "image_column": "image",
            "caption_column": "text"
        },
        "training_spec": {
            "base_model": "black-forest-labs/FLUX.1-dev",
            "lora_rank": 16,
            "lora_alpha": 32,
            "iteration_count": 1000,
            "batch_size": 2,
            "learning_rate": 0.0001,
            "resolution": [512, 768]
        }
    }'::jsonb,
    '0.25',
    '3.0',
    '1.0',
    '0.0',
    TRUE
),
(
    'image_lora_incremental_default',
    'Default template for incremental image LoRA training',
    'image_lora_creation',
    '{
        "theme": "manga_style",
        "target_platform": "executor",
        "deployment_target": "executor_node",
        "training_mode": "incremental",
        "dataset_spec": {
            "source": "huggingface",
            "repository_id": "kokoro/manga-style-dataset-v2",
            "sample_count": 150,
            "image_column": "image",
            "caption_column": "text"
        },
        "training_spec": {
            "base_model": "black-forest-labs/FLUX.1-dev",
            "lora_rank": 16,
            "lora_alpha": 32,
            "iteration_count": 800,
            "batch_size": 2,
            "learning_rate": 0.00005,
            "resolution": [512, 768]
        }
    }'::jsonb,
    '0.25',
    '3.0',
    '1.0',
    '0.0',
    TRUE
)
ON CONFLICT (name) DO NOTHING;

