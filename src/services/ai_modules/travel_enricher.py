#!/usr/bin/env python3
#4. ai_modules/travel_enricher.py - Travel Llama
"""Module Travel Llama pour enrichissement touristique"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class TravelEnricher:
    """Enrichissement touristique avec Travel Llama"""
    
    def __init__(self, ollama_client, config, models):
        self.client = ollama_client
        self.config = config
        self.models = models
        
    async def enrich(self, image_description: str, geo_context: Dict[str, str], 
                     callback=None) -> Optional[str]:
        """Enrichir avec des infos touristiques Travel Llama"""
        try:
            if callback:
                await callback('progress', 50, "Enrichissement Travel Llama...")
            
            # Vérifier si le modèle est configuré
            if 'travel_llama' not in self.models:
                logger.warning("Travel Llama non configuré")
                return None
            
            # Récupérer le prompt
            prompt_template = self.config.prompts_config.get('travel_enrichment', {}).get('main_prompt', '')
            params = self.config.prompts_config.get('travel_enrichment', {}).get('parameters', {})
            
            if not prompt_template:
                logger.warning("Pas de prompt Travel Llama")
                return None
            
            # Formatter le prompt
            formatted_prompt = prompt_template.format(
                location_basic=geo_context.get('location_basic', ''),
                cultural_context=geo_context.get('cultural_context', ''),
                nearby_attractions=geo_context.get('nearby_attractions', ''),
                image_description=image_description
            )
            
            # Appeler le modèle
            response = self.client.generate_text(
                model=self.models.get('travel_llama', 'llama3.1:70b'),
                prompt=formatted_prompt,
                temperature=params.get('temperature', 0.8),
                max_tokens=params.get('max_tokens', 200)
            )
            
            if response and len(response) > 30:
                if callback:
                    await callback('result', {
                        'step': 'travel_enrichment',
                        'result': {'enrichment': response[:100] + '...'}
                    })
                
                logger.info("✅ Travel Llama enrichissement réussi")
                return response
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Erreur Travel Llama: {e}")
            if callback:
                await callback('warning', f"Travel Llama non disponible: {e}")
            return None