#!/usr/bin/env python3
"""
📍 src/api/sse_routes.py

Routes API pour Server-Sent Events (SSE)
Génération asynchrone avec progression en temps réel
"""

from flask import Blueprint, request, jsonify, Response, current_app
import logging
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any

# Import des services et utilitaires
from utils.sse_manager import get_sse_manager
from utils.image_utils import get_image_processor
from config.server_config import ServerConfig

logger = logging.getLogger(__name__)

# Créer le blueprint
sse_bp = Blueprint('sse', __name__)


@sse_bp.route('/ai/generate-caption-stream/<request_id>')
def generate_caption_stream(request_id):
    """
    Endpoint SSE pour génération avec progression en temps réel
    """
    def event_stream():
        """Générateur de flux SSE"""
        sse_manager = get_sse_manager()
        connection = sse_manager.create_connection(request_id)
        
        try:
            # Message de connexion établie
            yield f"data: {json.dumps({'event': 'connected', 'message': 'Connexion SSE établie'})}\n\n"
            
            # Boucle de lecture des messages
            while connection.is_active:
                # Récupérer un message
                message = connection.get_message()
                
                if message:
                    # Formater et envoyer le message SSE
                    sse_response = sse_manager.format_sse_response(message)
                    yield sse_response
                    
                    # Si c'est un message de fin, arrêter le flux
                    if message.get('event') in ['complete', 'error']:
                        break
                else:
                    # Heartbeat pour maintenir la connexion
                    heartbeat = {
                        'event': 'heartbeat',
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    yield f"data: {json.dumps(heartbeat)}\n\n"
                    
        except GeneratorExit:
            # Client a fermé la connexion
            logger.info(f"Client déconnecté: {request_id}")
        finally:
            # Nettoyer la connexion
            sse_manager.close_connection(request_id)
    
    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control',
            'X-Accel-Buffering': 'no'  # Désactiver buffering nginx
        }
    )


@sse_bp.route('/ai/generate-caption-async', methods=['POST'])
def generate_caption_async():
    """
    Endpoint pour démarrer une génération asynchrone avec SSE
    
    Body JSON:
    {
        "request_id": "unique-id",
        "asset_id": "uuid-immich", 
        "image_base64": "data:image/jpeg;base64,/9j/4AAQ...",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "existing_caption": "Ancienne légende...",
        "language": "français",
        "style": "creative"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Corps JSON requis',
                'code': 'INVALID_JSON'
            }), 400
        
        request_id = data.get('request_id')
        if not request_id:
            return jsonify({
                'success': False,
                'error': 'request_id requis pour SSE',
                'code': 'MISSING_REQUEST_ID'
            }), 400
        
        # Valider les autres paramètres
        validation_error = validate_async_params(data)
        if validation_error:
            return validation_error
        
        # Récupérer l'app pour le contexte
        app = current_app._get_current_object()
        
        # Démarrer le traitement en arrière-plan
        thread = threading.Thread(
            target=process_generation_async,
            args=(request_id, data, app),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'request_id': request_id,
            'message': 'Génération démarrée, connectez-vous au flux SSE',
            'sse_url': f'/api/ai/generate-caption-stream/{request_id}'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur démarrage génération async: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'code': 'ASYNC_START_ERROR'
        }), 500


@sse_bp.route('/ai/regenerate-final', methods=['POST'])
def regenerate_final():
    """
    Régénérer uniquement la légende finale à partir des contextes modifiés
    
    Body JSON:
    {
        "image_description": "Description modifiée...",
        "geo_context": "Contexte géo modifié...", 
        "cultural_enrichment": "Enrichissement modifié...",
        "language": "français",
        "style": "creative"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Corps JSON requis'
            }), 400
        
        # Extraire les paramètres
        image_description = data.get('image_description', '')
        geo_context = data.get('geo_context', '')
        cultural_enrichment = data.get('cultural_enrichment', '')
        language = data.get('language', 'français')
        style = data.get('style', 'creative')
        
        logger.info("♻️ Régénération légende finale")
        
        # Récupérer le service IA
        ai_service = current_app.config.get('SERVICES', {}).get('ai_service')
        
        if not ai_service:
            return jsonify({
                'success': False,
                'error': 'Service IA non disponible'
            }), 503
        
        # Préparer le contexte enrichi pour Mistral
        enriched_context = {
            'location_basic': geo_context,
            'cultural_context': geo_context,
            'cultural_enrichment': cultural_enrichment,
            'nearby_attractions': '',
            'geographic_context': ''
        }
        
        # Générer uniquement avec Mistral
        prompts_used = {}
        raw_caption = ai_service._generate_creative_caption(
            image_description,
            enriched_context,
            language,
            style,
            prompts_used
        )
        
        # Post-traitement
        final_caption = ai_service.config.clean_caption(raw_caption)
        
        logger.info("✅ Légende finale régénérée")
        
        return jsonify({
            'success': True,
            'caption': final_caption,
            'raw_caption': raw_caption,
            'confidence_score': 0.8,  # Score fixe pour régénération
            'language': language,
            'style': style,
            'generation_time': 0.1,
            'method': 'regenerated',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur régénération finale: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'code': 'REGENERATION_ERROR'
        }), 500


def validate_async_params(data: Dict[str, Any]):
    """Valider les paramètres pour génération asynchrone"""
    required = ['asset_id', 'image_base64', 'latitude', 'longitude']
    
    for field in required:
        if field not in data or data[field] is None:
            return jsonify({
                'success': False,
                'error': f'Paramètre manquant: {field}',
                'code': f'MISSING_{field.upper()}'
            }), 400
    
    # Valider les coordonnées
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


def process_generation_async(request_id: str, data: Dict[str, Any], app):
    """Fonction de traitement en arrière-plan pour génération asynchrone"""
    sse_manager = get_sse_manager()
    
    with app.app_context():
        try:
            logger.info(f"🎨 Démarrage génération async pour {request_id}")
            
            # Extraire les paramètres
            asset_id = data['asset_id']
            image_base64 = data['image_base64']
            latitude = float(data['latitude'])
            longitude = float(data['longitude'])
            language = data.get('language', 'français')
            style = data.get('style', 'creative')
            
            # Récupérer les services
            services = app.config.get('SERVICES', {})
            ai_service = services.get('ai_service')
            geo_service = services.get('geo_service')
            
            if not ai_service or not geo_service:
                raise ValueError("Services non disponibles")
            
            # Étape 1: Préparation
            sse_manager.broadcast_progress(request_id, 'preparation', 5, 'Préparation de l\'image...')
            
            # Sauvegarder l'image
            image_processor = get_image_processor()
            temp_image_path = image_processor.save_base64_image(image_base64, asset_id)
            
            if not temp_image_path:
                sse_manager.broadcast_error(request_id, 'Erreur traitement image')
                return
            
            sse_manager.broadcast_progress(request_id, 'preparation', 10, 'Image préparée')
            
            try:
                # Étape 2: Analyse d'image
                sse_manager.broadcast_progress(request_id, 'image_analysis', 15, 'Analyse avec LLaVA...')
                
                prompts_used = {}
                image_analysis = ai_service._analyze_image_with_llava(Path(temp_image_path), prompts_used)
                
                sse_manager.broadcast_progress(request_id, 'image_analysis', 30, 'Analyse d\'image terminée')
                sse_manager.broadcast_result(request_id, 'image_analysis', {
                    'description': image_analysis['description'],
                    'confidence': image_analysis['confidence'],
                    'model': image_analysis['model_used']
                })
                
                # Étape 3: Géolocalisation
                sse_manager.broadcast_progress(request_id, 'geolocation', 35, 'Géolocalisation en cours...')
                
                geo_location = geo_service.get_location_info(latitude, longitude)
                geo_summary = geo_service.get_location_summary_for_ai(geo_location)
                
                sse_manager.broadcast_progress(request_id, 'geolocation', 50, 'Géolocalisation terminée')
                sse_manager.broadcast_result(request_id, 'geolocation', {
                    'location_basic': geo_summary.get('location_basic', ''),
                    'cultural_context': geo_summary.get('cultural_context', ''),
                    'confidence': geo_location.confidence_score
                })
                
                # Étape 4: Enrichissement culturel
                cultural_enrichment = ""
                if geo_location.confidence_score > 0.5 and geo_summary.get('cultural_context'):
                    sse_manager.broadcast_progress(request_id, 'cultural_enrichment', 55, 'Enrichissement culturel...')
                    
                    try:
                        cultural_enrichment = ai_service._enrich_cultural_context(geo_summary, prompts_used)
                        if cultural_enrichment:
                            sse_manager.broadcast_progress(request_id, 'cultural_enrichment', 65, 'Enrichissement terminé')
                            sse_manager.broadcast_result(request_id, 'cultural_enrichment', {
                                'enrichment': cultural_enrichment
                            })
                    except Exception as e:
                        logger.warning(f"Erreur enrichissement culturel: {e}")
                
                # Étape 5: Génération légende
                sse_manager.broadcast_progress(request_id, 'caption_generation', 70, 'Génération créative...')
                
                enriched_context = geo_summary.copy()
                if cultural_enrichment:
                    enriched_context['cultural_enrichment'] = cultural_enrichment
                
                raw_caption = ai_service._generate_creative_caption(
                    image_analysis['description'],
                    enriched_context,
                    language,
                    style,
                    prompts_used
                )
                
                sse_manager.broadcast_progress(request_id, 'caption_generation', 85, 'Légende générée')
                sse_manager.broadcast_result(request_id, 'raw_caption', {
                    'caption': raw_caption
                })
                
                # Étape 6: Post-traitement
                sse_manager.broadcast_progress(request_id, 'post_processing', 90, 'Finalisation...')
                
                final_caption = ai_service.config.clean_caption(raw_caption)
                confidence_score = ai_service._calculate_confidence_score(
                    image_analysis, geo_location, final_caption
                )
                
                # Étape 7: Résultat final
                sse_manager.broadcast_progress(request_id, 'completion', 100, 'Génération terminée!')
                
                final_result = {
                    'success': True,
                    'asset_id': asset_id,
                    'caption': final_caption,
                    'confidence_score': confidence_score,
                    'language': language,
                    'style': style,
                    'intermediate_results': {
                        'image_analysis': {
                            'description': image_analysis['description'],
                            'confidence': image_analysis['confidence']
                        },
                        'geo_context': {
                            'location_basic': geo_summary.get('location_basic', ''),
                            'cultural_context': geo_summary.get('cultural_context', ''),
                            'confidence': geo_location.confidence_score
                        },
                        'cultural_enrichment': cultural_enrichment,
                        'raw_caption': raw_caption
                    },
                    'metadata': {
                        'coordinates': [latitude, longitude],
                        'existing_caption': data.get('existing_caption', ''),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                }
                
                sse_manager.broadcast_complete(request_id, final_result)
                logger.info(f"✅ Génération async terminée pour {request_id}")
                
            finally:
                # Nettoyer fichier temporaire
                try:
                    import os
                    os.unlink(temp_image_path)
                except Exception:
                    pass
                    
        except Exception as e:
            logger.error(f"❌ Erreur génération async: {e}")
            sse_manager.broadcast_error(request_id, str(e))