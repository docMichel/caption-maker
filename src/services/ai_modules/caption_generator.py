#!/usr/bin/env python3
#5. ai_modules/caption_generator.py - Génération de légendes
"""Module de génération de légendes créatives"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class CaptionGenerator:
    """Générateur de légendes avec différents styles"""
    
    def __init__(self, ollama_client, config, models):
        self.client = ollama_client
        self.config = config
        self.models = models
        
    async def generate(self, context: Dict[str, str], language: str, style: str, 
                      callback=None) -> str:
        """Générer une légende créative"""
        try:
            if callback:
                await callback('progress', 70, f"Génération légende {style}...")
            
            # Récupérer le template
            prompt_template = self.config.get_caption_prompt(language, style)
            
            # Formatter avec toutes les données
            formatted_prompt = prompt_template.format(**context)
            
            if self.config.get_debug_config().get('log_prompts', False):
                logger.info(f"📝 PROMPT Caption ({language}/{style}):\n{formatted_prompt[:300]}...")

            # Générer
            caption = self.client.generate_text(
                model=self.models['caption'],
                prompt=formatted_prompt,
                temperature=0.8,
                max_tokens=250
            )
            
            if not caption:
                raise ValueError("Pas de légende générée")
            
            # Post-traitement
            caption = self.config.clean_caption(caption)
            
            if callback:
                await callback('result', {
                    'step': 'caption_generation',
                    'result': {'caption': caption}
                })
            
            logger.info("✅ Légende générée")
            return caption
            
        except Exception as e:
            logger.error(f"❌ Erreur génération: {e}")
            # Fallback
            return self.config.get_fallback_message(language, 'generic_error')