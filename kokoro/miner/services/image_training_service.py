from typing import Dict, Any, Optional
from kokoro.common.utils.logging import setup_logger
from kokoro.common.config.yaml_config import YamlConfig
import asyncio
import os
import torch
from pathlib import Path

logger = setup_logger(__name__)

try:
    from diffusers import DiffusionPipeline, StableDiffusionPipeline, UNet2DConditionModel
    from diffusers.optimization import get_scheduler
    from diffusers.training_utils import EMAModel
    from datasets import load_dataset
    DIFFUSERS_AVAILABLE = True
except ImportError:
    DIFFUSERS_AVAILABLE = False
    logger.warning("Diffusers not available")

try:
    from peft import LoraConfig, get_peft_model
    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False
    logger.warning("PEFT not available")


class ImageTrainingService:
    
    def __init__(self, config: Optional[YamlConfig] = None):
        self.config = config
        self.models_dir = Path("./models")
        self.models_dir.mkdir(exist_ok=True)
    
    async def train_lora(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not DIFFUSERS_AVAILABLE:
            raise RuntimeError("Diffusers library not available")
        
        workflow_id = task.get('workflow_id')
        logger.info(f"Starting image LoRA training for task {workflow_id}")
        
        workflow_spec = task.get("workflow_spec", {})
        training_spec = workflow_spec.get("training_spec", {})
        dataset_spec = workflow_spec.get("dataset_spec", {})
        
        image_config = self.config.get_image_training_config() if self.config else {}
        
        base_model = training_spec.get("base_model", image_config.get("base_model", "black-forest-labs/FLUX.1-dev"))
        lora_rank = training_spec.get("lora_rank", image_config.get("default_lora_rank", 16))
        lora_alpha = training_spec.get("lora_alpha", image_config.get("default_lora_alpha", 32))
        iteration_count = training_spec.get("iteration_count", image_config.get("default_iteration_count", 1000))
        batch_size = training_spec.get("batch_size", image_config.get("default_batch_size", 2))
        learning_rate = training_spec.get("learning_rate", image_config.get("default_learning_rate", 1e-4))
        resolution = training_spec.get("resolution", image_config.get("default_resolution", [512, 768]))
        
        training_mode = workflow_spec.get("training_mode", "new")
        base_lora_url = workflow_spec.get("base_lora_url")
        
        datasets_config = self.config.get_datasets_config() if self.config else {}
        image_dataset_config = datasets_config.get("image", {})
        
        dataset_repo = dataset_spec.get("repository_id", image_dataset_config.get("repository_id", "kokoro/manga-style-dataset"))
        image_column = dataset_spec.get("image_column", image_dataset_config.get("image_column", "image"))
        caption_column = dataset_spec.get("caption_column", image_dataset_config.get("caption_column", "text"))
        sample_count = dataset_spec.get("sample_count", 200)
        
        try:
            logger.info(f"Loading base model: {base_model}")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            if "flux" in base_model.lower():
                pipe = DiffusionPipeline.from_pretrained(
                    base_model,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32
                )
            else:
                pipe = StableDiffusionPipeline.from_pretrained(
                    base_model,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32
                )
            
            pipe = pipe.to(device)
            
            if training_mode == "incremental" and base_lora_url:
                logger.info(f"Incremental training: Loading base LoRA from {base_lora_url}")
                pipe.load_lora_weights(base_lora_url)
            else:
                logger.info("New training: Starting from base model")
            
            if PEFT_AVAILABLE:
                target_modules = ["to_k", "to_q", "to_v", "to_out.0"]
                if hasattr(pipe.unet.config, "attention_head_dim"):
                    target_modules = ["to_k", "to_q", "to_v", "to_out.0"]
                
                lora_config = LoraConfig(
                    r=lora_rank,
                    lora_alpha=lora_alpha,
                    init_lora_weights="gaussian",
                    target_modules=target_modules
                )
                
                pipe.unet = get_peft_model(pipe.unet, lora_config)
            
            logger.info(f"Loading dataset: {dataset_repo}")
            dataset = load_dataset(dataset_repo, split=f"train[:{sample_count}]")
            
            def preprocess_function(examples):
                images = examples[image_column] if image_column in examples else examples.get("image", [])
                captions = examples[caption_column] if caption_column in examples else examples.get("text", [])
                
                processed_images = []
                processed_captions = []
                
                for img, caption in zip(images, captions):
                    if isinstance(img, str):
                        from PIL import Image
                        import requests
                        img = Image.open(requests.get(img, stream=True).raw)
                    
                    if img.size[0] != resolution[0] or img.size[1] != resolution[1]:
                        img = img.resize(resolution, Image.Resampling.LANCZOS)
                    
                    processed_images.append(img)
                    processed_captions.append(str(caption))
                
                return {"image": processed_images, "text": processed_captions}
            
            processed_dataset = dataset.map(preprocess_function, batched=True, remove_columns=dataset.column_names)
            
            model_path = self.models_dir / workflow_id
            model_path.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"Starting {'incremental' if training_mode == 'incremental' else 'new'} training...")
            
            optimizer = torch.optim.AdamW(
                pipe.unet.parameters(),
                lr=learning_rate,
                betas=(0.9, 0.999),
                weight_decay=0.01,
                eps=1e-8
            )
            
            num_train_timesteps = pipe.scheduler.config.num_train_timesteps
            total_steps = 0
            
            for epoch in range(iteration_count // len(processed_dataset) + 1):
                for batch_idx, batch in enumerate(processed_dataset):
                    if total_steps >= iteration_count:
                        break
                    
                    images = batch["image"]
                    prompts = batch["text"]
                    
                    if isinstance(images, list):
                        from PIL import Image as PILImage
                        import torchvision.transforms as transforms
                        transform = transforms.Compose([
                            transforms.Resize(resolution),
                            transforms.ToTensor(),
                            transforms.Normalize([0.5], [0.5])
                        ])
                        image_tensors = torch.stack([transform(img) for img in images]).to(device)
                    else:
                        image_tensors = images.to(device)
                    
                    with torch.no_grad():
                        latents = pipe.vae.encode(image_tensors).latent_dist.sample()
                        latents = latents * pipe.vae.config.scaling_factor
                    
                    if isinstance(prompts, str):
                        prompts = [prompts]
                    
                    prompt_embeds = pipe._encode_prompt(
                        prompts,
                        device,
                        1,
                        False
                    )
                    
                    noise = torch.randn_like(latents)
                    timesteps = torch.randint(0, num_train_timesteps, (latents.shape[0],), device=device)
                    
                    noisy_latents = pipe.scheduler.add_noise(latents, noise, timesteps)
                    
                    model_pred = pipe.unet(
                        noisy_latents,
                        timesteps,
                        prompt_embeds
                    ).sample
                    
                    loss = torch.nn.functional.mse_loss(model_pred.float(), noise.float(), reduction="mean")
                    
                    loss.backward()
                    optimizer.step()
                    optimizer.zero_grad()
                    
                    total_steps += 1
                    
                    if total_steps % 100 == 0:
                        logger.info(f"Step {total_steps}/{iteration_count}, Loss: {loss.item()}")
                    
                    if total_steps >= iteration_count:
                        break
                
                if total_steps >= iteration_count:
                    break
            
            logger.info("Saving model...")
            pipe.save_pretrained(str(model_path))
            
            logger.info(f"Image LoRA training completed for task {workflow_id}")
            
            return {
                "status": "completed",
                "model_url": f"https://huggingface.co/kokoro/lora_{workflow_id}",
                "training_steps": iteration_count,
                "model_path": str(model_path),
                "training_mode": training_mode
            }
        except Exception as e:
            logger.error(f"Image LoRA training failed: {e}", exc_info=True)
            raise

