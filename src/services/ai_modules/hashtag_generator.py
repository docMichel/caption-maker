#!/usr/bin/env python3
#6. ai_modules/hashtag_generator.py - Hashtags

"""Module de génération de hashtags pour réseaux sociaux"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class HashtagGenerator:
    """Générateur de hashtags Instagram"""
    
    def __init__(self, ollama_client, config, models):
        self.client = ollama_client
        self.config = config
        self.models = models
        
    def generate(self, context: Dict[str, str]) -> List[str]:
        """Générer des hashtags pertinents"""
        try:
            prompt_template = self.config.prompts_config.get('hashtags_generation', {}).get('prompt', '')
            params = self.config.prompts_config.get('hashtags_generation', {}).get('parameters', {})
            
            if not prompt_template:
                return []
            
            formatted_prompt = prompt_template.format(**context)
            
            response = self.client.generate_text(
                model=self.models['caption'],
                prompt=formatted_prompt,
                temperature=params.get('temperature', 0.6),
                max_tokens=params.get('max_tokens', 50)
            )
            
            if response:
                # Parser les hashtags
                hashtags = [tag.strip() for tag in response.split() if tag.startswith('#')]
                logger.info(f"✅ {len(hashtags)} hashtags générés")
                return hashtags[:10]
            
            return []
            
        except Exception as e:
            logger.error(f"❌ Erreur hashtags: {e}")
            return []