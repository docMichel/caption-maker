#!/usr/bin/env python3
"""
📍 src/api/routes.py

Routes API principales pour la génération de légendes
Endpoint synchrone classique
"""

from flask import Blueprint, request, jsonify
import logging
import time
from typing import Dict, Any

# Import des services et utilitaires
from ..services.ai_service import AIService
from ..services.geo_service import GeoService
from ..services.immich_api_service import ImmichAPIService
from ..utils.image_utils import get_image_processor
from ..utils.cache_manager import get_generation_cache
from ..config.server_config import ServerConfig

logger = logging.getLogger(__name__)

# Créer le blueprint
api_bp = Blueprint('api', __name__)

# Variables globales pour tracking
active_requests = 0


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Vérification santé du serveur"""
    try:
        # Récupérer les services depuis le contexte Flask
        from flask import current_app
        services = current_app.config.get('SERVICES', {})
        
        # Vérifier les services
        services_status = {
            'geo_service': services.get('geo_service') is not None,
            'ai_service': services.get('ai_service') is not None,
            'immich_service': services.get('immich_service') is not None
        }
        
        # Tester la base de données
        db_status = False
        if services.get('geo_service'):
            try:
                services['geo_service'].connect_db()
                services['geo_service'].disconnect_db()
                db_status = True
            except Exception:
                pass
        
        # Tester Ollama
        ollama_status = False
        if services.get('ai_service'):
            try:
                models_status = services['ai_service'].get_available_models()
                ollama_status = len(models_status.get('missing', [])) == 0
            except Exception:
                pass
        
        status = {
            'status': 'healthy' if all(services_status.values()) else 'partial',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'services': services_status,
            'database': db_status,
            'ollama': ollama_status,
            'active_requests': active_requests,
            'cache_size': get_generation_cache().get_stats()['size']
        }
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur health check: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }), 500


@api_bp.route('/ai/generate-caption', methods=['POST'])
def generate_caption():
    """
    Endpoint principal pour génération de légendes (synchrone)
    
    Body JSON:
    {
        "asset_id": "uuid-immich",
        "image_base64": "data:image/jpeg;base64,/9j/4AAQ...",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "existing_caption": "Ancienne légende...",
        "language": "français",
        "style": "creative"
    }
    """
    global active_requests
    
    try:
        # Vérifier le nombre de requêtes actives
        if active_requests >= ServerConfig.MAX_CONCURRENT_REQUESTS:
            return jsonify({
                'success': False,
                'error': 'Trop de requêtes simultanées, réessayez plus tard',
                'code': 'TOO_MANY_REQUESTS'
            }), 429
        
        active_requests += 1
        request_start_time = time.time()
        
        # Valider les données d'entrée
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Corps JSON requis',
                'code': 'INVALID_JSON'
            }), 400
        
        # Extraire les paramètres
        asset_id = data.get('asset_id')
        image_base64 = data.get('image_base64')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        existing_caption = data.get('existing_caption', '')
        language = data.get('language', 'français')
        style = data.get('style', 'creative')
        
        # Validation des paramètres obligatoires
        validation_error = validate_generation_params(
            asset_id, image_base64, latitude, longitude
        )
        if validation_error:
            return validation_error
        
        # Vérifier le cache
        cache = get_generation_cache()
        cached_result = cache.get_caption(
            asset_id, latitude, longitude, language, style
        )
        
        if cached_result:
            logger.info(f"📍 Cache hit pour {asset_id}")
            active_requests -= 1
            return jsonify({
                'success': True,
                'cached': True,
                **cached_result
            })
        
        logger.info(f"🎨 Génération légende pour asset {asset_id} ({latitude}, {longitude})")
        
        # Sauvegarder l'image temporairement
        image_processor = get_image_processor()
        temp_image_path = image_processor.save_base64_image(image_base64, asset_id)
        
        if not temp_image_path:
            return jsonify({
                'success': False,
                'error': 'Erreur traitement image',
                'code': 'IMAGE_PROCESSING_ERROR'
            }), 400
        
        try:
            # Récupérer les services
            from flask import current_app
            services = current_app.config.get('SERVICES', {})
            ai_service = services.get('ai_service')
            immich_service = services.get('immich_service')
            
            if not ai_service:
                raise ValueError("Service IA non disponible")
            
            # Enrichir avec données de visages si disponible
            face_context = {}
            if immich_service:
                try:
                    faces_info = immich_service.get_asset_faces(asset_id)
                    if faces_info:
                        face_context = immich_service.generate_face_context_for_ai(faces_info)
                        logger.info(f"👥 Contexte visages: {face_context.get('social_context', 'N/A')}")
                except Exception as e:
                    logger.warning(f"⚠️  Erreur récupération visages: {e}")
            
            # Générer la légende avec l'IA
            generation_result = ai_service.generate_caption(
                image_path=temp_image_path,
                latitude=float(latitude),
                longitude=float(longitude),
                language=language,
                style=style
            )
            
            # Préparer la réponse
            response_data = prepare_response_data(
                generation_result, asset_id, face_context, 
                existing_caption, latitude, longitude
            )
            
            # Mettre en cache le résultat
            cache.set_caption(
                response_data, asset_id, latitude, longitude, language, style
            )
            
            processing_time = time.time() - request_start_time
            logger.info(f"✅ Légende générée en {processing_time:.1f}s")
            
            return jsonify(response_data)
            
        finally:
            # Nettoyer le fichier temporaire
            try:
                import os
                os.unlink(temp_image_path)
            except Exception:
                pass
            
    except Exception as e:
        logger.error(f"❌ Erreur génération légende: {e}")
        return jsonify({
            'success': False,
            'error': f'Erreur interne: {str(e)}',
            'code': 'INTERNAL_ERROR'
        }), 500
        
    finally:
        active_requests -= 1


def validate_generation_params(asset_id, image_base64, latitude, longitude):
    """Valider les paramètres de génération"""
    if not asset_id:
        return jsonify({
            'success': False,
            'error': 'asset_id requis',
            'code': 'MISSING_ASSET_ID'
        }), 400
    
    if not image_base64:
        return jsonify({
            'success': False,
            'error': 'image_base64 requise',
            'code': 'MISSING_IMAGE'
        }), 400
    
    if latitude is None or longitude is None:
        return jsonify({
            'success': False,
            'error': 'Coordonnées GPS requises (latitude, longitude)',
            'code': 'MISSING_COORDINATES'
        }), 400
    
    # Valider les coordonnées
    try:
        lat = float(latitude)
        lon = float(longitude)
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ValueError("Coordonnées invalides")
    except (ValueError, TypeError):
        return jsonify({
            'success': False,
            'error': 'Coordonnées GPS invalides',
            'code': 'INVALID_COORDINATES'
        }), 400
    
    return None


def prepare_response_data(generation_result, asset_id, face_context, 
                         existing_caption, latitude, longitude):
    """Préparer les données de réponse"""
    response_data = {
        'success': True,
        'cached': False,
        'asset_id': asset_id,
        'generation_time': generation_result.generation_time_seconds,
        'confidence_score': generation_result.confidence_score,
        
        # Légende finale
        'caption': generation_result.caption,
        'language': generation_result.language,
        'style': generation_result.style,
        
        # Contextes intermédiaires
        'intermediate_results': {
            'image_analysis': {
                'description': generation_result.intermediate_results.get(
                    'image_analysis_raw', {}
                ).get('description', ''),
                'confidence': generation_result.intermediate_results.get(
                    'image_analysis_raw', {}
                ).get('confidence', 0),
                'model': generation_result.intermediate_results.get(
                    'image_analysis_raw', {}
                ).get('model_used', '')
            },
            'geo_context': {
                'location_basic': generation_result.intermediate_results.get(
                    'geo_summary_basic', {}
                ).get('location_basic', ''),
                'cultural_context': generation_result.intermediate_results.get(
                    'geo_summary_basic', {}
                ).get('cultural_context', ''),
                'nearby_attractions': generation_result.intermediate_results.get(
                    'geo_summary_basic', {}
                ).get('nearby_attractions', ''),
                'confidence': generation_result.geo_context.get('confidence_score', 0)
            },
            'cultural_enrichment': generation_result.intermediate_results.get(
                'cultural_enrichment_raw', ''
            ),
            'raw_caption': generation_result.intermediate_results.get('caption_raw', ''),
            'face_context': face_context
        },
        
        # Métadonnées
        'metadata': {
            'coordinates': [latitude, longitude],
            'models_used': generation_result.ai_models_used,
            'processing_steps': generation_result.processing_steps,
            'existing_caption': existing_caption,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    }
    
    # Analyse de comparaison si ancienne légende
    if existing_caption:
        response_data['comparison'] = analyze_caption_improvement(
            existing_caption, generation_result
        )
    
    return response_data


def analyze_caption_improvement(original: str, generated_result) -> Dict[str, Any]:
    """Analyser les améliorations par rapport à l'ancienne légende"""
    try:
        improvements = []
        
        # Longueur
        if len(generated_result.caption) > len(original):
            improvements.append("Plus détaillée")
        
        # Contexte géographique
        geo_context = generated_result.intermediate_results.get('geo_summary_basic', {})
        if geo_context.get('location_basic'):
            improvements.append("Contexte géographique ajouté")
        
        # Contexte culturel
        if generated_result.intermediate_results.get('cultural_enrichment_raw'):
            improvements.append("Enrichissement culturel")
        
        # Style
        if generated_result.style == 'creative':
            improvements.append("Style plus créatif")
        
        return {
            'improvements': improvements,
            'original_length': len(original),
            'generated_length': len(generated_result.caption),
            'confidence_boost': generated_result.confidence_score
        }
        
    except Exception as e:
        logger.warning(f"Erreur analyse amélioration: {e}")
        return {'improvements': [], 'error': str(e)}