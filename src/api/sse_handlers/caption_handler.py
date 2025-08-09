#!/usr/bin/env python3
"""Handler pour la génération asynchrone de légendes"""

import logging
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from flask import jsonify

from utils.sse_manager import get_sse_manager
from utils.image_utils import get_image_processor

logger = logging.getLogger(__name__)


class CaptionGenerationHandler:
    """Gestion de la génération asynchrone"""
    
    def validate_params(self, data: Dict[str, Any]):
        """Valider les paramètres de génération"""
        required = ['asset_id']  # image_base64 optionnel si Immich
        
        for field in required:
            if field not in data or data[field] is None:
                return jsonify({
                    'success': False,
                    'error': f'Paramètre manquant: {field}',
                    'code': f'MISSING_{field.upper()}'
                }), 400
        
        # Valider les coordonnées si présentes
        if 'latitude' in data and 'longitude' in data:
            if data['latitude'] is not None and data['longitude'] is not None:
                try:
                    lat = float(data['latitude'])
                    lon = float(data['longitude'])
                    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                        raise ValueError("Coordonnées invalides")
                except (ValueError, TypeError):
                    return jsonify({
                        'success': False,
                        'error': 'Coordonnées GPS invalides',
                        'code': 'INVALID_COORDINATES'
                    }), 400
        
        return None
    
    def process_async(self, request_id: str, data: Dict[str, Any], app):
        """Traitement asynchrone avec événements SSE au format standard"""
        with app.app_context():
            sse_manager = get_sse_manager()
            
            # Envoyer l'événement connected
            sse_manager.broadcast_connected(request_id)
            
            try:
                logger.info(f"🎨 Démarrage génération async pour {request_id}")
                
                # Extraire les paramètres
                asset_id = data['asset_id']
                language = data.get('language', 'français')
                style = data.get('style', 'creative')
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                
                # Étape 1: Préparation
                self._handle_image_preparation(
                    request_id, data, app, sse_manager
                )
                
                # Étape 2: Génération avec callback SSE
                result = self._generate_with_ai_service(
                    request_id, data, app, sse_manager
                )
                
                # Étape 3: Résultat final au format standard
                self._send_final_result(
                    request_id, result, asset_id, sse_manager
                )
                
            except TimeoutError as e:
                logger.error(f"⏱️ Timeout: {e}")
                sse_manager.broadcast_error(
                    request_id, f"Timeout: {str(e)}", "TIMEOUT", "processing"
                )
            except Exception as e:
                logger.error(f"❌ Erreur: {e}")
                sse_manager.broadcast_error(
                    request_id, str(e), "UNKNOWN_ERROR", "processing"
                )
    
    def _handle_image_preparation(self, request_id: str, data: Dict[str, Any], 
                                 app, sse_manager):
        """Gérer la préparation de l'image"""
        sse_manager.broadcast_progress(
            request_id, 'preparation', 5, 'Préparation de l\'image...'
        )
        
        image_base64 = data.get('image_base64')
        
        # Si pas d'image base64, essayer de télécharger depuis Immich
        if not image_base64:
            immich_service = app.config.get('SERVICES', {}).get('immich_service')
            if immich_service:
                image_base64 = self._download_from_immich(
                    data['asset_id'], immich_service, sse_manager, request_id
                )
            else:
                raise ValueError("Image requise: image_base64 ou service Immich")
        
        # Sauvegarder temporairement
        image_processor = get_image_processor()
        temp_path = image_processor.save_base64_image(image_base64, data['asset_id'])
        
        if not temp_path:
            raise ValueError("Erreur traitement image")
        
        data['_temp_image_path'] = temp_path
        sse_manager.broadcast_progress(
            request_id, 'preparation', 10, 'Image préparée'
        )
    
    def _generate_with_ai_service(self, request_id: str, data: Dict[str, Any],
                                 app, sse_manager):
        """Générer avec le service IA et callbacks SSE"""
        services = app.config.get('SERVICES', {})
        ai_service = services.get('ai_service')
        
        if not ai_service:
            raise ValueError("Service IA non disponible")
        
        # Callback pour transformer les événements
        async def sse_callback(event_type, *args):
            """Transformer les événements AI en format SSE standard"""
            if event_type == 'progress':
                progress, message = args
                step = self._determine_step(message)
                sse_manager.broadcast_progress(request_id, step, progress, message)
                
            elif event_type == 'result':
                result_data = args[0]
                self._send_partial_result(request_id, result_data, sse_manager)
                
            elif event_type == 'warning':
                message = args[0] if args else "Avertissement"
                code = 'MODEL_FALLBACK' if 'llama' in message.lower() else 'WARNING'
                sse_manager.broadcast_warning(request_id, message, code)
                
            elif event_type == 'error':
                error = args[0] if args else "Erreur inconnue"
                sse_manager.broadcast_error(
                    request_id, str(error), "GENERATION_ERROR", "processing"
                )
        
        # Lancer la génération
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                ai_service.generate_caption_async(
                    image_path=data['_temp_image_path'],
                    latitude=data.get('latitude'),
                    longitude=data.get('longitude'),
                    language=data.get('language', 'français'),
                    style=data.get('style', 'creative'),
                    include_hashtags=data.get('include_hashtags', True),
                    callback=sse_callback
                )
            )
            return result
        finally:
            loop.close()
            # Nettoyer le fichier temporaire
            self._cleanup_temp_file(data.get('_temp_image_path'))
    
    def _send_final_result(self, request_id: str, result, asset_id: str, 
                          sse_manager):
        """Envoyer le résultat final au format standard"""
        # Envoyer les hashtags si présents
        if result.hashtags and len(result.hashtags) > 0:
            sse_manager.broadcast_partial(request_id, 'hashtags', {
                'tags': result.hashtags,
                'count': len(result.hashtags)
            })
        
        intermediate = result.intermediate_results

        # Préparer et envoyer le résultat complet
        sse_manager.broadcast_complete(
            request_id,
            success=True,
            caption=result.caption,
            hashtags=result.hashtags,
            confidence_score=result.confidence_score,
            language=result.language,
            style=result.style,
            processing_time=result.generation_time_seconds,
            asset_id=asset_id,
            models_used={
                'vision': intermediate.get('image_analysis', {}).get('model_used', 'llava:7b'),
                'cultural': 'qwen2:7b',
                'travel': intermediate.get('travel_model', 'llama3.2:3b'),
                'caption': 'mistral:7b-instruct'
            },
            # AJOUTER CES ENRICHISSEMENTS
            enrichments={
                'geo_context': intermediate.get('geo_context', {}),
                'travel_enrichment': intermediate.get('travel_enrichment', ''),
                'image_analysis': intermediate.get('image_analysis', {}),
                'cultural_enrichment': intermediate.get('cultural_enrichment', '')
            }
        )

    
    def _determine_step(self, message: str) -> str:
        """Déterminer l'étape depuis le message"""
        message_lower = message.lower()
        if 'image' in message_lower:
            return 'image_analysis'
        elif 'géo' in message_lower:
            return 'geolocation'
        elif 'travel llama' in message_lower:
            return 'travel_enrichment'
        elif 'culturel' in message_lower:
            return 'cultural_enrichment'
        elif 'légende' in message_lower:
            return 'caption_generation'
        elif 'hashtag' in message_lower:
            return 'hashtag_generation'
        else:
            return 'processing'
    
    def _send_partial_result(self, request_id: str, result_data: Dict, sse_manager):
        """Envoyer un résultat partiel au bon format"""
        step = result_data.get('step')
        result = result_data.get('result', {})
        
        # Mapper vers le format attendu
        if step == 'image_analysis':
            sse_manager.broadcast_partial(request_id, 'image_analysis', {
                'description': result.get('description', ''),
                'confidence': result.get('confidence', 0),
                'model': 'llava:7b'
            })
        elif step == 'geolocation':
            sse_manager.broadcast_partial(request_id, 'geolocation', {
                'location': result.get('location_basic', ''),
                'coordinates': result.get('coordinates', []),
                'confidence': result.get('confidence', 0),
                'nearby_places': result.get('nearby_places', []),
                'cultural_sites': result.get('cultural_sites', []),
                'address': result.get('address', ''),  # AJOUTER
                'city': result.get('city', ''),        # AJOUTER
                'country': result.get('country', ''),   # AJOUTER
                'stats': result.get('stats', {})       # AJOUTER
            })
    
    def _download_from_immich(self, asset_id: str, immich_service, 
                            sse_manager, request_id: str) -> str:
        """Télécharger l'image depuis Immich"""
        logger.info(f"📥 Téléchargement depuis Immich pour {asset_id}")
        sse_manager.broadcast_progress(
            request_id, 'preparation', 8, 'Téléchargement depuis Immich...'
        )
        
        image_data = immich_service.download_asset_image(asset_id)
        if not image_data:
            raise ValueError(f"Impossible de télécharger l'image {asset_id}")
        
        import base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        return f"data:image/jpeg;base64,{image_base64}"
    
    def _cleanup_temp_file(self, temp_path: Optional[str]):
        """Nettoyer le fichier temporaire"""
        if temp_path:
            try:
                import os
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Nettoyage fichier temp: {e}")