#!/usr/bin/env python3
"""
AIService - Orchestrateur modulaire pour génération de légendes
Version simplifiée et modulaire
"""

import logging
import time
import asyncio
from typing import Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass

# Import des modules
from .ai_modules.ollama_client import OllamaClient
from .ai_modules.image_analyzer import ImageAnalyzer
from .ai_modules.travel_enricher import TravelEnricher
from .ai_modules.caption_generator import CaptionGenerator
from .ai_modules.hashtag_generator import HashtagGenerator

# Import de la config
from config.ai_config import AIConfig
from .geo_service import GeoService, GeoLocation

logger = logging.getLogger(__name__)

@dataclass
class CaptionResult:
    """Résultat de génération"""
    caption: str
    hashtags: list
    language: str
    style: str
    confidence_score: float
    generation_time_seconds: float
    intermediate_results: dict
    processing_steps: list
    error_messages: list = None

class AIService:
    """Service orchestrateur modulaire"""
    
    def __init__(self, geo_service: GeoService, config_path: Optional[str] = None):
        self.geo_service = geo_service
        self.config = AIConfig(config_path)
        
        # Configuration Ollama
        ollama_config = self.config.get_ollama_config()
        self.ollama_client = OllamaClient(
            base_url=ollama_config['base_url'],
            timeout=ollama_config['timeout'],
            max_retries=ollama_config['max_retries']
        )
        
        # Modèles
        self.models = self.config.get_models()
        
        # Initialiser les modules
        self.image_analyzer = ImageAnalyzer(self.ollama_client, self.config, self.models)
        self.travel_enricher = TravelEnricher(self.ollama_client, self.config, self.models)
        self.caption_generator = CaptionGenerator(self.ollama_client, self.config, self.models)
        self.hashtag_generator = HashtagGenerator(self.ollama_client, self.config, self.models)
        
        logger.info("🤖 AIService modulaire initialisé")
    
    async def generate_caption_async(
        self, 
        image_path: str, 
        latitude: Optional[float], 
        longitude: Optional[float],
        language: str = 'français', 
        style: str = 'creative',
        include_hashtags: bool = True,
        callback=None
    ) -> CaptionResult:
        """Génération asynchrone avec support SSE"""
        
        start_time = time.time()
        processing_steps = []
        intermediate_results = {}
        error_messages = []
        
        try:
            # 1. Analyse d'image
            image_result = await self.image_analyzer.analyze(
                Path(image_path), 
                callback
            )
            intermediate_results['image_analysis'] = image_result
            processing_steps.append("✅ Analyse d'image")
            
            # 2. Contexte géographique
            geo_context = {}
            if latitude and longitude:
                if callback:
                    await callback('progress', 35, 'Géolocalisation en cours...')
    
                geo_location = self.geo_service.get_location_info(latitude, longitude)
                geo_context = self.geo_service.get_location_summary_for_ai(geo_location)
                intermediate_results['geo_context'] = geo_context
                processing_steps.append("✅ Contexte géographique")

                if callback:
                    await callback('partial', {
                        'type': 'geolocation',
                        'content': {
                            'location': geo_context.get('location_basic', ''),
                            'coordinates': [latitude, longitude],
                            'confidence': geo_location.confidence_score,
                            'nearby_places': [],
                            'cultural_sites': []
                        }
                    })
            else:
                processing_steps.append("⚠️ Pas de géolocalisation")
            
            # 3. Travel Llama (optionnel)
            travel_enrichment = None
            if geo_context and geo_context.get('location_basic'):
                travel_enrichment = await self.travel_enricher.enrich(
                    image_result['description'],
                    geo_context,
                    callback
                )
                if travel_enrichment:
                    geo_context['travel_enrichment'] = travel_enrichment
                    intermediate_results['travel_enrichment'] = travel_enrichment
                    processing_steps.append("✅ Travel Llama")
                else:
                    processing_steps.append("⚠️ Travel Llama non disponible")
            
            # 4. Préparer le contexte final
            caption_context = {
                    'image_description': image_result.get('description', ''),
                    'location_basic': geo_context.get('location_basic', ''),
                    'cultural_context': geo_context.get('cultural_context', ''),
                    'nearby_attractions': geo_context.get('nearby_attractions', ''),
                    'travel_enrichment': travel_enrichment or '',
                    'cultural_enrichment': geo_context.get('cultural_enrichment', ''),  # Si présent
                    'geographic_context': geo_context.get('geographic_context', '')
                }

            # S'assurer qu'aucune valeur n'est None
            caption_context = {k: v or '' for k, v in caption_context.items()}
            
            # 5. Générer la légende
            caption = await self.caption_generator.generate(
                caption_context,
                language,
                style,
                callback
            )
            intermediate_results['caption'] = caption
            processing_steps.append("✅ Légende générée")
            
            # 6. Générer les hashtags
            hashtags = []
            if include_hashtags:
                hashtags = self.hashtag_generator.generate(caption_context)
                intermediate_results['hashtags'] = hashtags
                processing_steps.append(f"✅ {len(hashtags)} hashtags")
            
            # 7. Calculer le score de confiance
            confidence = self._calculate_confidence(
                image_result,
                geo_context,
                bool(travel_enrichment),
                caption
            )
            
            generation_time = time.time() - start_time
            
            if callback:
                await callback('complete', {
                    'success': True,
                    'caption': caption,
                    'hashtags': hashtags,
                    'confidence_score': confidence
                })
            
            return CaptionResult(
                caption=caption,
                hashtags=hashtags,
                language=language,
                style=style,
                confidence_score=confidence,
                generation_time_seconds=generation_time,
                intermediate_results=intermediate_results,
                processing_steps=processing_steps,
                error_messages=error_messages
            )
            
        except Exception as e:
            logger.error(f"❌ Erreur génération: {e}")
            error_messages.append(str(e))
            
            if callback:
                await callback('error', str(e))
            
            # Retourner un résultat avec fallback
            return CaptionResult(
                caption=self.config.get_fallback_message(language, 'generic_error'),
                hashtags=[],
                language=language,
                style='fallback',
                confidence_score=0.1,
                generation_time_seconds=time.time() - start_time,
                intermediate_results=intermediate_results,
                processing_steps=processing_steps,
                error_messages=error_messages
            )
    
    def generate_caption(self, *args, **kwargs) -> CaptionResult:
        """Version synchrone pour compatibilité"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.generate_caption_async(*args, **kwargs)
            )
        finally:
            loop.close()
    
    def _calculate_confidence(self, image_result, geo_context, has_travel, caption):
        """Calcul simplifié du score de confiance"""
        score = 0.0
        
        # Image (30%)
        score += image_result.get('confidence', 0.5) * 0.3
        
        # Géo (30%)
        if geo_context:
            score += 0.3
        
        # Travel Llama (20%)
        if has_travel:
            score += 0.2
        
        # Longueur légende (20%)
        caption_len = len(caption.split())
        if 40 <= caption_len <= 120:
            score += 0.2
        elif 20 <= caption_len < 40:
            score += 0.1
        
        return min(score, 0.95)