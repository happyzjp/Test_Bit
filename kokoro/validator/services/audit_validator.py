from typing import Dict, Any, Optional
import torch
from PIL import Image
from kokoro.validator.schemas.audit import AuditTaskRequest
from kokoro.validator.services.quality_evaluator import QualityEvaluator
from kokoro.validator.services.content_filter import ContentFilter
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)

try:
    import clip
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
    logger.warning("CLIP not available, using fallback")

try:
    from diffusers import DiffusionPipeline, StableDiffusionPipeline
    DIFFUSERS_AVAILABLE = True
except ImportError:
    DIFFUSERS_AVAILABLE = False
    logger.warning("Diffusers not available, using fallback")

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers not available, using fallback")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("Sentence transformers not available, using fallback")


class AuditValidator:
    def __init__(self):
        self.quality_evaluator = QualityEvaluator()
        self.content_filter = ContentFilter()
        self.clip_model = None
        self.clip_preprocess = None
        self.text_encoder = None
        self._load_models()
    
    def _load_models(self):
        try:
            if CLIP_AVAILABLE:
                self.clip_model, self.clip_preprocess = clip.load("ViT-L/14", device="cuda" if torch.cuda.is_available() else "cpu")
            else:
                self.clip_model = None
                self.clip_preprocess = None
            
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                self.text_encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            else:
                self.text_encoder = None
            
            logger.info("Models loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            self.clip_model = None
            self.clip_preprocess = None
            self.text_encoder = None
    
    async def process_audit_task(self, request: AuditTaskRequest) -> Dict[str, Any]:
        task_info = request.task_info
        task_type = task_info.get("task_type", "image_lora")
        
        cosine_similarity = await self._validate_lora(task_info, request.lora_url, task_type)
        
        generated_content = await self._generate_content(task_info, request.lora_url, task_type)
        
        quality_score = await self.quality_evaluator.evaluate_quality(
            task_type,
            generated_content
        )
        
        content_safety_score = 0.0
        if task_type == "image_lora":
            content_safety_score = await self.content_filter.detect_content(generated_content)
            if content_safety_score >= 0.7:
                logger.warning(f"Content safety violation detected: {content_safety_score}")
                return {
                    "audit_task_id": request.audit_task_id,
                    "miner_hotkey": request.miner_hotkey,
                    "cosine_similarity": cosine_similarity,
                    "quality_score": 0.0,
                    "final_score": 0.0,
                    "rejected": True,
                    "reason": "Content safety violation"
                }
        
        final_score = self._calculate_final_score(cosine_similarity, quality_score)
        
        return {
            "audit_task_id": request.audit_task_id,
            "miner_hotkey": request.miner_hotkey,
            "cosine_similarity": cosine_similarity,
            "quality_score": quality_score,
            "final_score": final_score,
            "content_safety_score": content_safety_score
        }
    
    async def _validate_lora(
        self,
        task_info: Dict[str, Any],
        lora_url: str,
        task_type: str
    ) -> float:
        prompt = task_info.get("prompt", "")
        seed = task_info.get("seed", 42)
        base_model = task_info.get("base_model", "")
        target_vector = task_info.get("target_vector", [])
        
        if not target_vector:
            logger.warning("No target vector provided, using default similarity")
            return 0.85
        
        try:
            generated_content = await self._generate_content(task_info, lora_url, task_type)
            
            if task_type == "image_lora":
                current_vector = self._extract_image_features(generated_content)
            else:
                current_vector = self._extract_text_features(generated_content)
            
            target_tensor = torch.tensor(target_vector, device="cuda" if torch.cuda.is_available() else "cpu")
            
            if current_vector.shape != target_tensor.shape:
                logger.warning(f"Vector shape mismatch: {current_vector.shape} vs {target_tensor.shape}")
                return 0.0
            
            cosine_sim = torch.cosine_similarity(
                current_vector.unsqueeze(0),
                target_tensor.unsqueeze(0)
            ).item()
            
            return max(0.0, min(1.0, cosine_sim))
        except Exception as e:
            logger.error(f"LoRA validation failed: {e}")
            return 0.0
    
    async def _generate_content(
        self,
        task_info: Dict[str, Any],
        lora_url: str,
        task_type: str
    ) -> Any:
        prompt = task_info.get("prompt", "")
        seed = task_info.get("seed", 42)
        base_model = task_info.get("base_model", "")
        
        if not DIFFUSERS_AVAILABLE and not TRANSFORMERS_AVAILABLE:
            logger.error("Required libraries not available")
            return None
        
        generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(seed)
        
        if task_type == "image_lora" or task_type == "image_lora_creation":
            if not DIFFUSERS_AVAILABLE:
                logger.error("Diffusers not available for image generation")
                return None
            
            try:
                if "flux" in base_model.lower():
                    pipe = DiffusionPipeline.from_pretrained(base_model, torch_dtype=torch.float16)
                else:
                    pipe = StableDiffusionPipeline.from_pretrained(base_model, torch_dtype=torch.float16)
                
                pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")
                
                try:
                    pipe.load_lora_weights(lora_url)
                except Exception as e:
                    logger.warning(f"Failed to load LoRA weights: {e}")
                
                image = pipe(prompt, generator=generator, num_inference_steps=30).images[0]
                return image
            except Exception as e:
                logger.error(f"Image generation failed: {e}")
                return None
        else:
            if not TRANSFORMERS_AVAILABLE:
                logger.error("Transformers not available for text generation")
                return None
            
            try:
                tokenizer = AutoTokenizer.from_pretrained(base_model)
                model = AutoModelForCausalLM.from_pretrained(
                    base_model,
                    torch_dtype=torch.float16,
                    device_map="auto"
                )
                
                try:
                    from peft import PeftModel
                    model = PeftModel.from_pretrained(model, lora_url)
                except Exception as e:
                    logger.warning(f"Failed to load LoRA weights: {e}")
                
                inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
                outputs = model.generate(**inputs, max_length=512, do_sample=True, temperature=0.7)
                text = tokenizer.decode(outputs[0], skip_special_tokens=True)
                return text
            except Exception as e:
                logger.error(f"Text generation failed: {e}")
                return None
    
    def _extract_image_features(self, image: Image.Image) -> torch.Tensor:
        if not CLIP_AVAILABLE or self.clip_model is None:
            return torch.randn(512)
        
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            image_input = self.clip_preprocess(image).unsqueeze(0).to(device)
            with torch.no_grad():
                features = self.clip_model.encode_image(image_input)
                features = features / features.norm(dim=-1, keepdim=True)
            return features.squeeze(0)
        except Exception as e:
            logger.error(f"Image feature extraction failed: {e}")
            return torch.randn(512)
    
    def _extract_text_features(self, text: str) -> torch.Tensor:
        if not SENTENCE_TRANSFORMERS_AVAILABLE or self.text_encoder is None:
            return torch.randn(384)
        
        try:
            features = self.text_encoder.encode(text, convert_to_tensor=True)
            features = features / features.norm(dim=-1, keepdim=True)
            return features.squeeze(0)
        except Exception as e:
            logger.error(f"Text feature extraction failed: {e}")
            return torch.randn(384)
    
    def _calculate_final_score(
        self,
        cosine_similarity: float,
        quality_score: float
    ) -> float:
        base_score = cosine_similarity * 10.0
        
        combined_score = (base_score + quality_score) / 2.0
        
        if combined_score < 3.5:
            return 0.0
        
        return combined_score

