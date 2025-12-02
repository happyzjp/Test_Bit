from typing import Dict, Any, Optional
from kokoro.common.utils.logging import setup_logger
from kokoro.common.config.yaml_config import YamlConfig
import asyncio
import os
import torch
from pathlib import Path

logger = setup_logger(__name__)

try:
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer, DataCollatorForLanguageModeling
    from datasets import load_dataset
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers not available")


class TextTrainingService:
   
    
    def __init__(self, config: Optional[YamlConfig] = None):
        self.config = config
        self.models_dir = Path("./models")
        self.models_dir.mkdir(exist_ok=True)
    
    async def train_lora(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError("Transformers library not available")
        
        workflow_id = task.get('workflow_id')
        logger.info(f"Starting text LoRA training for task {workflow_id}")
        
        workflow_spec = task.get("workflow_spec", {})
        training_spec = workflow_spec.get("training_spec", {})
        dataset_spec = workflow_spec.get("dataset_spec", {})
        
        text_config = self.config.get_text_training_config() if self.config else {}
        
        base_model = training_spec.get("base_model", text_config.get("base_model", "Qwen/Qwen3-0.6B-Instruct"))
        lora_rank = training_spec.get("lora_rank", text_config.get("default_lora_rank", 16))
        lora_alpha = training_spec.get("lora_alpha", text_config.get("default_lora_alpha", 32))
        iteration_count = training_spec.get("iteration_count", text_config.get("default_iteration_count", 1000))
        batch_size = training_spec.get("batch_size", text_config.get("default_batch_size", 4))
        learning_rate = training_spec.get("learning_rate", text_config.get("default_learning_rate", 2e-4))
        max_length = training_spec.get("max_length", text_config.get("default_max_length", 512))
        
        training_mode = workflow_spec.get("training_mode", "new")
        base_lora_url = workflow_spec.get("base_lora_url")
        
        datasets_config = self.config.get_datasets_config() if self.config else {}
        text_dataset_config = datasets_config.get("text", {})
        
        dataset_repo = dataset_spec.get("repository_id", text_dataset_config.get("repository_id", "kokoro/japanese-culture-qa-dataset"))
        question_column = dataset_spec.get("question_column", text_dataset_config.get("question_column", "question"))
        answer_column = dataset_spec.get("answer_column", text_dataset_config.get("answer_column", "answer"))
        sample_count = dataset_spec.get("sample_count", 2000)
        
        try:
            logger.info(f"Loading base model: {base_model}")
            tokenizer = AutoTokenizer.from_pretrained(base_model)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            
            model = AutoModelForCausalLM.from_pretrained(
                base_model,
                torch_dtype=torch.float16,
                device_map="auto"
            )
            
            if training_mode == "incremental" and base_lora_url:
                logger.info(f"Incremental training: Loading base LoRA from {base_lora_url}")
                model = PeftModel.from_pretrained(model, base_lora_url)
            else:
                logger.info("New training: Starting from base model")
            
            lora_config = LoraConfig(
                r=lora_rank,
                lora_alpha=lora_alpha,
                target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
                lora_dropout=0.05,
                bias="none",
                task_type=TaskType.CAUSAL_LM
            )
            
            model = get_peft_model(model, lora_config)
            
            logger.info(f"Loading dataset: {dataset_repo}")
            dataset = load_dataset(dataset_repo, split=f"train[:{sample_count}]")
            
            def preprocess_function(examples):
                questions = examples[question_column] if question_column in examples else examples.get("question", [])
                answers = examples[answer_column] if answer_column in examples else examples.get("answer", [])
                
                texts = []
                for q, a in zip(questions, answers):
                    text = f"Question: {q}\nAnswer: {a}"
                    texts.append(text)
                
                return tokenizer(texts, truncation=True, padding=True, max_length=max_length, return_tensors="pt")
            
            tokenized_dataset = dataset.map(preprocess_function, batched=True, remove_columns=dataset.column_names)
            
            data_collator = DataCollatorForLanguageModeling(
                tokenizer=tokenizer,
                mlm=False
            )
            
            model_path = self.models_dir / workflow_id
            model_path.mkdir(parents=True, exist_ok=True)
            
            training_args = TrainingArguments(
                output_dir=str(model_path),
                num_train_epochs=1,
                per_device_train_batch_size=batch_size,
                learning_rate=learning_rate,
                logging_steps=100,
                save_steps=500,
                max_steps=iteration_count,
                save_total_limit=2,
                load_best_model_at_end=False,
                report_to="none"
            )
            
            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=tokenized_dataset,
                data_collator=data_collator
            )
            
            logger.info(f"Starting {'incremental' if training_mode == 'incremental' else 'new'} training...")
            trainer.train()
            
            logger.info("Saving model...")
            model.save_pretrained(str(model_path))
            tokenizer.save_pretrained(str(model_path))
            
            logger.info(f"Text LoRA training completed for task {workflow_id}")
            
            return {
                "status": "completed",
                "model_url": f"https://huggingface.co/kokoro/lora_{workflow_id}",
                "training_steps": iteration_count,
                "model_path": str(model_path),
                "training_mode": training_mode,
                "final_loss": trainer.state.log_history[-1].get("loss", 0.0) if trainer.state.log_history else 0.0
            }
        except Exception as e:
            logger.error(f"Text LoRA training failed: {e}", exc_info=True)
            raise

