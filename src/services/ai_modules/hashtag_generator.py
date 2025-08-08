#!/usr/bin/env python3
#6. ai_modules/hashtag_generator.py - Hashtags

#!/usr/bin/env python3
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
            # Utiliser les méthodes de config appropriées
            prompt_template = self.config.get_hashtag_prompt()
            params = self.config.get_hashtag_params()
            
            if not prompt_template:
                logger.warning("Pas de template pour hashtags, utilisation fallback")
                # Fallback simple
                location = context.get('location_basic', '').replace(' ', '').replace(',', '')
                return [f"#{location}", "#travel", "#photography", "#wanderlust"]
            
            # Formatter le prompt
            formatted_prompt = prompt_template.format(**context)
            
            # Générer
            response = self.client.generate_text(
                model=self.models.get('caption', 'mistral:7b-instruct'),
                prompt=formatted_prompt,
                temperature=params.get('temperature', 0.6),
                max_tokens=params.get('max_tokens', 50)
            )
            
            if response:
                # Parser les hashtags
                hashtags = [tag.strip() for tag in response.split() if tag.startswith('#')]
                logger.info(f"✅ {len(hashtags)} hashtags générés")
                return hashtags[:10]
            
            # Fallback si pas de réponse
            return self._generate_fallback_hashtags(context)
            
        except Exception as e:
            logger.error(f"❌ Erreur hashtags: {e}")
            return self._generate_fallback_hashtags(context)
    
    def _generate_fallback_hashtags(self, context: Dict[str, str]) -> List[str]:
        """Générer des hashtags de fallback basiques"""
        hashtags = []
        
        # Lieu
        location = context.get('location_basic', '')
        if location:
            # Nettoyer et créer hashtag
            clean_location = ''.join(c for c in location if c.isalnum() or c.isspace())
            parts = clean_location.split()[:2]  # Max 2 mots
            if parts:
                hashtags.append(f"#{''.join(parts)}")
        
        # Ajouter des hashtags génériques
        hashtags.extend(['#travel', '#photography', '#wanderlust', '#explore'])
        
        return hashtags[:8]