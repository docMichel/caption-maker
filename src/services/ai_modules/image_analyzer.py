
#!/usr/bin/env python3
#services/ai_modules/image_analyzer.py - Module vision
"""Module d'analyse d'image avec LLaVA"""

import base64
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ImageAnalyzer:
    """Analyseur d'images avec modèle vision"""
    
    def __init__(self, ollama_client, config, models):
        self.client = ollama_client
        self.config = config
        self.models = models
        
    async def analyze(self, image_path: Path, callback=None) -> Dict[str, Any]:
        """Analyser une image avec LLaVA"""
        try:
            if callback:
                await callback('progress', 10, "Analyse de l'image avec LLaVA...")
            
            # Récupérer le prompt depuis la config
            prompt = self.config.get_image_analysis_prompt(detailed=False)
            params = self.config.get_image_analysis_params()
            
            # Encoder l'image
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            if self.config.get_debug_config().get('log_prompts', False):
                logger.info(f"📝 PROMPT LLaVA:\n{prompt[:200]}...")

            # Préparer la requête
            payload = {
                'model': self.models['vision'],
                'prompt': prompt,
                'images': [image_base64],
                'stream': False,
                'options': {
                    'temperature': params.get('temperature', 0.6),
                    'num_predict': params.get('max_tokens', 200),
                    'top_p': params.get('top_p', 0.9)
                }
            }
            
            response = self.client.call_with_retry('generate', payload)
            
            if not response:
                raise ValueError("Pas de réponse LLaVA")
            
            description = response.get('response', '').strip()
            
            result = {
                'description': description,
                'confidence': 0.8,
                'model_used': self.models['vision']
            }
            
            if callback:
                await callback('result', {
                    'step': 'image_analysis',
                    'result': result
                })
            
            logger.info("✅ Analyse d'image terminée")
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur analyse image: {e}")
            # Retourner un résultat fallback
            return {
                'description': 'Image analysée',
                'confidence': 0.3,
                'model_used': 'fallback',
                'error': str(e)
            }