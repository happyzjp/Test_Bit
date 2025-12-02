from typing import Dict, Any, Optional
from PIL import Image
import torch
from kokoro.common.utils.logging import setup_logger

logger = setup_logger(__name__)


class QualityEvaluator:
    def __init__(self):
        self.aesthetic_model = None
        self._load_aesthetic_model()
    
    def _load_aesthetic_model(self):
        try:
            from transformers import CLIPProcessor, CLIPModel
            self.aesthetic_model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
            self.aesthetic_processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
            logger.info("Aesthetic model loaded")
        except Exception as e:
            logger.warning(f"Failed to load aesthetic model: {e}")
            self.aesthetic_model = None
            self.aesthetic_processor = None
    
    async def evaluate_quality(
        self,
        task_type: str,
        content: Any
    ) -> float:
        if task_type == "text_lora" or task_type == "text_lora_creation":
            return await self._evaluate_text_quality(content)
        elif task_type == "image_lora" or task_type == "image_lora_creation":
            return await self._evaluate_image_quality(content)
        else:
            return 5.0
    
    async def _evaluate_text_quality(self, text: Optional[str]) -> float:
        if text is None:
            return 5.0
        
        relevance_score = self._evaluate_relevance(text)
        accuracy_score = self._evaluate_accuracy(text)
        fluency_score = self._evaluate_fluency(text)
        cultural_accuracy = self._evaluate_cultural_accuracy(text)
        
        return (relevance_score + accuracy_score + fluency_score + cultural_accuracy) / 4.0
    
    def _evaluate_relevance(self, text: str) -> float:
        japanese_keywords = ["日本", "文化", "传统", "和", "茶道", "武士", "樱花", "神社"]
        score = 5.0
        for keyword in japanese_keywords:
            if keyword in text:
                score += 0.5
        return min(10.0, score)
    
    def _evaluate_accuracy(self, text: str) -> float:
        return 8.0
    
    def _evaluate_fluency(self, text: str) -> float:
        if len(text) < 10:
            return 5.0
        return 8.0
    
    def _evaluate_cultural_accuracy(self, text: str) -> float:
        return 8.0
    
    async def _evaluate_image_quality(self, image: Optional[Image.Image]) -> float:
        if image is None:
            return 5.0
        
        aesthetic_score = await self._calculate_aesthetic_score(image)
        composition_score = self._evaluate_composition(image)
        color_score = self._evaluate_color(image)
        detail_score = self._evaluate_detail(image)
        
        return (aesthetic_score * 0.5 + composition_score * 0.2 + color_score * 0.2 + detail_score * 0.1)
    
    async def _calculate_aesthetic_score(self, image: Image.Image) -> float:
        if self.aesthetic_model is None:
            return 7.0
        
        try:
            inputs = self.aesthetic_processor(images=image, return_tensors="pt")
            with torch.no_grad():
                outputs = self.aesthetic_model.get_image_features(**inputs)
                score = float(outputs.mean().item())
                normalized_score = (score + 1.0) / 2.0 * 10.0
                return min(10.0, max(0.0, normalized_score))
        except Exception as e:
            logger.warning(f"Aesthetic score calculation failed: {e}")
            return 7.0
    
    def _evaluate_composition(self, image: Image.Image) -> float:
        width, height = image.size
        aspect_ratio = width / height
        
        if 0.7 <= aspect_ratio <= 1.4:
            return 8.0
        else:
            return 6.0
    
    def _evaluate_color(self, image: Image.Image) -> float:
        colors = image.getcolors(maxcolors=256*256*256)
        if colors and len(colors) > 10:
            return 8.0
        return 6.0
    
    def _evaluate_detail(self, image: Image.Image) -> float:
        width, height = image.size
        if width >= 512 and height >= 512:
            return 8.0
        return 6.0

