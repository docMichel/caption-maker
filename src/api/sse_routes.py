#!/usr/bin/env python3
"""
📍 src/api/sse_routes.py

Routes API pour Server-Sent Events (SSE)
Génération asynchrone avec progression en temps réel
"""
# D'abord les imports système
import sys
from pathlib import Path
# Ajouter le chemin parent au PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# Maintenant les autres imports
from flask import Blueprint, request, jsonify, Response, current_app
import logging
import json
import time
import threading
from typing import Dict, Any

# Import des services et utilitaires (sans ..)
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
                        yield sse_response  # S'assurer que le message est envoyé
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
    required = ['asset_id', 'image_base64'] #, 'latitude', 'longitude']
    
    for field in required:
        if field not in data or data[field] is None:
            return jsonify({
                'success': False,
                'error': f'Paramètre manquant: {field}',
                'code': f'MISSING_{field.upper()}'
            }), 400
    
    # Valider les coordonnées
        if 'latitude' in data and 'longitude' in data and data['latitude'] is not None and data['longitude'] is not None:
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
    with app.app_context():
        # Imports absolus dans le contexte
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        from utils.sse_manager import get_sse_manager
        from utils.image_utils import get_image_processor
        import asyncio
        import time
        
        sse_manager = get_sse_manager()
        
        try:
            logger.info(f"🎨 Démarrage génération async pour {request_id}")
            
            # Extraire les paramètres
            asset_id = data['asset_id']
            language = data.get('language', 'français')
            style = data.get('style', 'creative')
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            if latitude is not None:
                latitude = float(latitude)
            if longitude is not None:
                longitude = float(longitude)

            # Récupérer les services
            services = app.config.get('SERVICES', {})
            ai_service = services.get('ai_service')
            geo_service = services.get('geo_service')
            immich_service = services.get('immich_service')

            if not ai_service or not geo_service:
                error_msg = "Services IA ou Geo non disponibles"
                logger.error(f"❌ {error_msg}")
                sse_manager.broadcast_error(request_id, error_msg)
                return
            
            # Étape 1: Préparation de l'image
            sse_manager.broadcast_progress(request_id, 'preparation', 5, 'Préparation de l\'image...')
            
            # Gérer image depuis base64 OU depuis immich_asset
            image_base64 = data.get('image_base64')
            
            if not image_base64 and immich_service:
                # Récupérer l'image depuis Immich
                logger.info(f"📥 Téléchargement de l'image depuis Immich pour {asset_id}")
                sse_manager.broadcast_progress(request_id, 'preparation', 8, 'Téléchargement depuis Immich...')
                
                try:
                    # Télécharger l'image binaire
                    image_data = immich_service.download_asset_image(asset_id)
                    
                    if image_data:
                        # Encoder en base64
                        import base64
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                        # Ajouter le préfixe data URL
                        image_base64 = f"data:image/jpeg;base64,{image_base64}"
                        logger.info(f"✅ Image téléchargée depuis Immich ({len(image_data)} bytes)")
                    else:
                        error_msg = f"Impossible de télécharger l'image {asset_id} depuis Immich"
                        logger.error(f"❌ {error_msg}")
                        sse_manager.broadcast_error(request_id, error_msg)
                        return
                        
                except Exception as e:
                    logger.error(f"❌ Erreur téléchargement Immich: {e}")
                    sse_manager.broadcast_error(request_id, f"Erreur téléchargement image: {str(e)}")
                    return
            
            elif not image_base64:
                # Ni base64 ni service Immich disponible
                error_msg = "Image requise: soit image_base64, soit service Immich configuré"
                logger.error(f"❌ {error_msg}")
                sse_manager.broadcast_error(request_id, error_msg)
                return

            # Sauvegarder l'image temporairement
            image_processor = get_image_processor()
            temp_image_path = image_processor.save_base64_image(image_base64, asset_id)
            
            if not temp_image_path:
                sse_manager.broadcast_error(request_id, 'Erreur traitement image')
                return
            
            sse_manager.broadcast_progress(request_id, 'preparation', 10, 'Image préparée')
            
            # Créer un callback pour les événements SSE
            async def sse_callback(event_type, *args):
                """Callback pour envoyer les events SSE depuis AIService"""
                if event_type == 'progress':
                    progress, message = args
                    sse_manager.broadcast_progress(request_id, 'processing', progress, message)
                    
                elif event_type == 'result':
                    result_data = args[0]
                    step = result_data.get('step', 'processing')
                    sse_manager.broadcast_result(request_id, step, result_data.get('result', {}))
                    
                elif event_type == 'warning':
                    message = args[0] if args else "Avertissement"
                    sse_manager.broadcast_progress(request_id, 'warning', -1, f"⚠️ {message}")
                    
                elif event_type == 'error':
                    error = args[0] if args else "Erreur inconnue"
                    sse_manager.broadcast_error(request_id, str(error))
                    
                elif event_type == 'complete':
                    data = args[0] if args else {}
                    sse_manager.broadcast_complete(request_id, data)
            
            try:
                # Créer une boucle d'événements pour l'async
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Utiliser la nouvelle méthode modulaire async
                result = loop.run_until_complete(
                    ai_service.generate_caption_async(
                        image_path=str(temp_image_path),
                        latitude=latitude,
                        longitude=longitude,
                        language=language,
                        style=style,
                        include_hashtags=data.get('include_hashtags', True),
                        callback=sse_callback
                    )
                )
                
                # Préparer le résultat final
                final_result = {
                    'success': True,
                    'asset_id': asset_id,
                    'caption': result.caption,
                    'hashtags': result.hashtags,
                    'confidence_score': result.confidence_score,
                    'language': result.language,
                    'style': result.style,
                    'intermediate_results': result.intermediate_results,
                    'metadata': {
                        'coordinates': [latitude, longitude] if latitude and longitude else None,
                        'existing_caption': data.get('existing_caption', ''),
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'generation_time': result.generation_time_seconds,
                        'processing_steps': result.processing_steps
                    }
                }
                
                # Si des erreurs mais quand même un résultat
                if result.error_messages:
                    final_result['warnings'] = result.error_messages
                
                # Envoyer le résultat final
                sse_manager.broadcast_complete(request_id, final_result)
                logger.info(f"✅ Génération async terminée pour {request_id} en {result.generation_time_seconds:.1f}s")
                
            finally:
                # Nettoyer la boucle d'événements
                loop.close()
                
                # Nettoyer fichier temporaire
                try:
                    import os
                    if temp_image_path and os.path.exists(temp_image_path):
                        os.unlink(temp_image_path)
                except Exception as e:
                    logger.warning(f"Impossible de supprimer l'image temporaire: {e}")
                    
        except TimeoutError as e:
            import traceback
            logger.error(f"⏱️ Timeout génération async: {e}")
            sse_manager.broadcast_error(request_id, f"Timeout: {str(e)}", "TIMEOUT")
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Erreur génération async: {e}")
            logger.error(f"Traceback complet:\n{traceback.format_exc()}")
            sse_manager.broadcast_error(request_id, str(e))