#!/usr/bin/env python3
"""Module Travel Llama pour enrichissement touristique"""

import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class TravelEnricher:
    """Enrichissement touristique avec Travel Llama"""
    
    def __init__(self, ollama_client, config, models):
        self.client = ollama_client
        self.config = config
        self.models = models
        self.travel_model = None
        self._tested_models = set()  # Pour éviter de tester plusieurs fois
    
    def _test_model_availability(self, model_name: str) -> bool:
        """Tester si un modèle est vraiment disponible"""
        if model_name in self._tested_models:
            return model_name == self.travel_model
            
        try:
            logger.info(f"🧪 Test de disponibilité du modèle: {model_name}")
            
            # Méthode 1: Essayer de lister les modèles
            try:
                response = requests.get(f"{self.client.base_url}/api/tags", timeout=5)
                if response.status_code == 200:
                    available_models = [m['name'] for m in response.json().get('models', [])]
                    if model_name in available_models:
                        logger.info(f"✅ {model_name} trouvé dans la liste des modèles")
                        self._tested_models.add(model_name)
                        return True
            except:
                pass
            
            # Méthode 2: Essayer une génération test rapide
            logger.info(f"🔧 Test direct du modèle {model_name}...")
            test_response = self.client.generate_text(
                model=model_name,
                prompt="Bonjour",
                max_tokens=5
            )
            
            if test_response:
                logger.info(f"✅ {model_name} répond correctement")
                self._tested_models.add(model_name)
                return True
            else:
                logger.warning(f"❌ {model_name} ne répond pas")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur test modèle {model_name}: {e}")
            return False
    
    def _get_travel_model(self):
        """Déterminer quel modèle utiliser avec test réel"""
        if self.travel_model is not None:
            return self.travel_model
            
        # Modèles à tester dans l'ordre
        primary_model = self.models.get('travel_llama', 'llama3.1:70b')
        fallback_model = self.models.get('travel_llama_fallback', 'mistral:7b-instruct')
        
        # Tester le modèle principal
        if self._test_model_availability(primary_model):
            self.travel_model = primary_model
            logger.info(f"🌍 Travel Llama principal actif: {self.travel_model}")
        else:
            # Tester le fallback
            logger.warning(f"⚠️ {primary_model} non disponible, test du fallback...")
            if self._test_model_availability(fallback_model):
                self.travel_model = fallback_model
                logger.info(f"🔄 Utilisation du fallback: {self.travel_model}")
            else:
                logger.error("❌ Aucun modèle Travel disponible!")
                self.travel_model = None
                
        return self.travel_model
    
    async def enrich(self, image_description: str, geo_context: Dict[str, str], 
                     callback=None) -> Optional[str]:
        """Enrichir avec des infos touristiques Travel Llama"""
        try:
            # Déterminer le modèle à utiliser
            model = self._get_travel_model()
            
            if not model:
                logger.warning("❌ Pas de modèle Travel disponible")
                if callback:
                    await callback('warning', 'Travel Llama non disponible', 'MODEL_UNAVAILABLE')
                return None
            
            if callback:
                model_info = f"Travel Llama ({model})"
                await callback('progress', 50, f"Enrichissement {model_info}...")
            
            # Récupérer le prompt depuis la config
            prompt_data = self.config._config.get('travel_enrichment', {})
            
            # Utiliser le prompt principal ou le fallback selon le modèle
            if model == self.models.get('travel_llama_fallback'):
                prompt_template = prompt_data.get('fallback_prompt', '')
                params = {'temperature': 0.7, 'max_tokens': 100}
            else:
                prompt_template = prompt_data.get('main_prompt', '')
                params = prompt_data.get('parameters', {})
            
            if not prompt_template:
                logger.warning("❌ Pas de prompt Travel Llama dans la config")
                return None
            
            # Formatter le prompt
            formatted_prompt = prompt_template.format(
                location_basic=geo_context.get('location_basic', ''),
                cultural_context=geo_context.get('cultural_context', ''),
                nearby_attractions=geo_context.get('nearby_attractions', ''),
                image_description=image_description
            )
            
            logger.debug(f"📝 Prompt Travel Llama ({len(formatted_prompt)} chars)")
            
            # Appeler le modèle
            response = self.client.generate_text(
                model=model,
                prompt=formatted_prompt,
                temperature=params.get('temperature', 0.8),
                max_tokens=params.get('max_tokens', 200)
            )
            
            if response and len(response) > 30:
                if callback:
                    await callback('result', {
                        'step': 'travel_enrichment',
                        'result': {'enrichment': response}
                    })
                    await callback('partial', {
                        'type': 'travel_enrichment',
                        'content': {
                            'text': response,
                            'source': 'travel_llama',
                            'model': model
                        }
                    })
                
                logger.info(f"✅ Travel Llama enrichissement réussi ({len(response)} chars)")
                return response
            else:
                logger.warning(f"⚠️ Réponse Travel Llama trop courte ou vide")
                return None
            
        except Exception as e:
            logger.error(f"❌ Erreur Travel Llama: {e}")
            import traceback
            traceback.print_exc()
            
            if callback:
                await callback('warning', f"Travel Llama erreur: {str(e)}", 'MODEL_ERROR')
            return None