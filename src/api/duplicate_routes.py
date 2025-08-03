#!/usr/bin/env python3
"""
📍 src/api/duplicate_routes.py

Routes API pour la détection de doublons d'images
Support SSE pour traitement asynchrone de nombreux assets
"""

from flask import Blueprint, request, jsonify, Response, current_app
import logging
import json
import time
import threading
from typing import Dict, Any, List
import uuid

# Import des utilitaires
from src.utils.sse_manager import get_sse_manager
from src.utils.cache_manager import get_generation_cache

logger = logging.getLogger(__name__)

# Créer le blueprint
duplicate_bp = Blueprint('duplicates', __name__)


@duplicate_bp.route('/duplicates/status', methods=['GET'])
def get_duplicate_status():
    """Vérifier le statut du service de détection de doublons"""
    try:
        # Récupérer le service
        duplicate_service = current_app.config.get('SERVICES', {}).get('duplicate_service')
        
        if not duplicate_service:
            return jsonify({
                'success': False,
                'clip_available': False,
                'error': 'Service de détection non disponible'
            }), 503
        
        return jsonify({
            'success': True,
            'clip_available': duplicate_service.clip_available,
            'model_info': duplicate_service.get_model_info(),
            'stats': duplicate_service.get_stats()
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur status doublons: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/find-similar', methods=['POST'])
def find_similar_sync():
    """
    Endpoint synchrone pour détection de doublons (petits lots)
    Pour compatibilité avec l'existant
    """
    try:
        data = request.get_json()
        selected_asset_ids = data.get('selected_asset_ids', [])
        threshold = data.get('threshold', 0.85)
        
        if not selected_asset_ids:
            return jsonify({
                'success': False,
                'error': 'Aucun asset sélectionné'
            }), 400
        
        # Pour moins de 10 assets, traitement synchrone
        if len(selected_asset_ids) <= 10:
            # Récupérer les services
            services = current_app.config.get('SERVICES', {})
            duplicate_service = services.get('duplicate_service')
            immich_service = services.get('immich_service')
            
            if not duplicate_service or not immich_service:
                return jsonify({
                    'success': False,
                    'error': 'Services non disponibles'
                }), 503
            
            # Traitement direct
            logger.info(f"🔍 Recherche doublons parmi {len(selected_asset_ids)} images")
            
            # Télécharger les images depuis Immich
            images = _download_images_from_immich(selected_asset_ids, immich_service)
            
            if not images:
                return jsonify({
                    'success': False,
                    'error': 'Impossible de récupérer les images'
                }), 500
            
            # Analyser avec le service
            groups = duplicate_service.find_duplicates(images, threshold)
            
            return jsonify({
                'success': True,
                'groups': groups,
                'total_groups': len(groups),
                'threshold': threshold
            })
        
        else:
            # Trop d'assets, suggérer l'API async
            return jsonify({
                'success': False,
                'error': f'Trop d\'assets ({len(selected_asset_ids)}). Utilisez l\'API asynchrone.',
                'suggestion': '/api/duplicates/find-similar-async'
            }), 400
            
    except Exception as e:
        logger.error(f"❌ Erreur find-similar: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/find-similar-async', methods=['POST'])
def find_similar_async():
    """
    Endpoint pour démarrer une détection asynchrone avec SSE
    
    Body JSON:
    {
        "request_id": "unique-id",
        "selected_asset_ids": ["id1", "id2", ...],
        "threshold": 0.85,
        "group_by_time": true,
        "time_window_hours": 24
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Corps JSON requis'
            }), 400
        
        # Générer un request_id si non fourni
        request_id = data.get('request_id') or f"dup-{uuid.uuid4().hex[:8]}"
        selected_asset_ids = data.get('selected_asset_ids', [])
        
        if not selected_asset_ids:
            return jsonify({
                'success': False,
                'error': 'Aucun asset sélectionné'
            }), 400
        
        # Récupérer l'app pour le contexte
        app = current_app._get_current_object()
        
        # Démarrer le traitement en arrière-plan
        thread = threading.Thread(
            target=process_duplicate_detection_async,
            args=(request_id, data, app),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'request_id': request_id,
            'message': f'Analyse de {len(selected_asset_ids)} images démarrée',
            'sse_url': f'/api/duplicates/find-similar-stream/{request_id}'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur démarrage async: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/find-similar-stream/<request_id>')
def find_similar_stream(request_id):
    """
    Endpoint SSE pour suivre la progression de la détection
    """
    def event_stream():
        """Générateur de flux SSE"""
        sse_manager = get_sse_manager()
        connection = sse_manager.create_connection(request_id)
        
        try:
            # Message de connexion
            yield f"data: {json.dumps({'event': 'connected', 'message': 'Connexion SSE établie'})}\n\n"
            
            # Boucle de lecture
            while connection.is_active:
                message = connection.get_message()
                
                if message:
                    sse_response = sse_manager.format_sse_response(message)
                    yield sse_response
                    
                    if message.get('event') in ['complete', 'error']:
                        break
                else:
                    # Heartbeat
                    heartbeat = {
                        'event': 'heartbeat',
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    yield f"data: {json.dumps(heartbeat)}\n\n"
                    
        except GeneratorExit:
            logger.info(f"Client déconnecté: {request_id}")
        finally:
            sse_manager.close_connection(request_id)
    
    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'X-Accel-Buffering': 'no'
        }
    )


@duplicate_bp.route('/duplicates/analyze-album/<album_id>', methods=['POST'])
def analyze_album_async(album_id):
    """
    Analyser un album complet pour trouver les doublons
    Utilise SSE pour la progression
    """
    try:
        data = request.get_json() or {}
        request_id = f"album-{album_id}-{int(time.time())}"
        
        # Préparer les données pour le traitement
        process_data = {
            'request_id': request_id,
            'album_id': album_id,
            'threshold': data.get('threshold', 0.85),
            'group_by_time': data.get('group_by_time', True),
            'time_window_hours': data.get('time_window_hours', 24)
        }
        
        # Récupérer l'app pour le contexte
        app = current_app._get_current_object()
        
        # Démarrer le traitement
        thread = threading.Thread(
            target=process_album_analysis_async,
            args=(request_id, process_data, app),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'request_id': request_id,
            'message': f'Analyse de l\'album {album_id} démarrée',
            'sse_url': f'/api/duplicates/find-similar-stream/{request_id}'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur analyse album: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def process_duplicate_detection_async(request_id: str, data: Dict[str, Any], app):
    """Traitement asynchrone de détection de doublons"""
    with app.app_context():
        sse_manager = get_sse_manager()
        
        try:
            logger.info(f"🔍 Démarrage détection async pour {request_id}")
            
            # Récupérer les paramètres
            selected_asset_ids = data['selected_asset_ids']
            threshold = data.get('threshold', 0.85)
            total_images = len(selected_asset_ids)
            
            # Récupérer les services
            services = app.config.get('SERVICES', {})
            duplicate_service = services.get('duplicate_service')
            immich_service = services.get('immich_service')
            
            if not duplicate_service or not immich_service:
                raise ValueError("Services non disponibles")
            
            # Étape 1: Téléchargement des images
            sse_manager.broadcast_progress(
                request_id, 'download', 5, 
                f'Téléchargement de {total_images} images...'
            )
            
            images = []
            for i, asset_id in enumerate(selected_asset_ids):
                try:
                    # Télécharger l'image
                    image_data = immich_service.download_asset_image(asset_id)
                    if image_data:
                        images.append({
                            'asset_id': asset_id,
                            'data': image_data
                        })
                    
                    # Progress update
                    progress = 5 + int((i + 1) / total_images * 30)
                    sse_manager.broadcast_progress(
                        request_id, 'download', progress,
                        f'Téléchargement: {i + 1}/{total_images}'
                    )
                    
                except Exception as e:
                    logger.warning(f"Erreur téléchargement {asset_id}: {e}")
            
            if not images:
                raise ValueError("Aucune image téléchargée")
            
            sse_manager.broadcast_result(request_id, 'download', {
                'downloaded': len(images),
                'total': total_images
            })
            
            # Étape 2: Encodage CLIP
            sse_manager.broadcast_progress(
                request_id, 'encoding', 40,
                'Analyse des images avec CLIP...'
            )
            
            # Encoder les images par batch
            embeddings = []
            batch_size = 10
            
            for i in range(0, len(images), batch_size):
                batch = images[i:i + batch_size]
                batch_embeddings = duplicate_service.encode_images_batch(batch)
                embeddings.extend(batch_embeddings)
                
                progress = 40 + int((i + batch_size) / len(images) * 30)
                sse_manager.broadcast_progress(
                    request_id, 'encoding', progress,
                    f'Encodage: {min(i + batch_size, len(images))}/{len(images)}'
                )
            
            # Étape 3: Calcul des similarités
            sse_manager.broadcast_progress(
                request_id, 'similarity', 75,
                'Calcul des similarités...'
            )
            
            # Calculer la matrice de similarité
            similarity_matrix = duplicate_service.compute_similarity_matrix(embeddings)
            
            # Étape 4: Regroupement
            sse_manager.broadcast_progress(
                request_id, 'grouping', 85,
                'Regroupement des doublons...'
            )
            
            groups = duplicate_service.group_similar_images(
                images, similarity_matrix, threshold
            )
            
            # Enrichir avec métadonnées Immich
            for group in groups:
                for img in group['images']:
                    asset_metadata = immich_service.get_asset_metadata(img['asset_id'])
                    if asset_metadata:
                        img.update({
                            'filename': asset_metadata.get('originalFileName', ''),
                            'date': asset_metadata.get('fileCreatedAt', ''),
                            'size': asset_metadata.get('exifInfo', {}).get('fileSizeInByte', 0)
                        })
            
            # Étape 5: Résultat final
            sse_manager.broadcast_progress(
                request_id, 'completion', 100,
                f'{len(groups)} groupes de doublons trouvés!'
            )
            
            final_result = {
                'success': True,
                'groups': groups,
                'total_groups': len(groups),
                'total_duplicates': sum(len(g['images']) - 1 for g in groups),
                'threshold': threshold,
                'processing_time': time.time() - time.time()  # À implémenter
            }
            
            sse_manager.broadcast_complete(request_id, final_result)
            logger.info(f"✅ Détection terminée pour {request_id}: {len(groups)} groupes")
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Erreur détection async: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            sse_manager.broadcast_error(request_id, str(e))


def process_album_analysis_async(request_id: str, data: Dict[str, Any], app):
    """Traitement asynchrone d'analyse d'album complet"""
    with app.app_context():
        sse_manager = get_sse_manager()
        
        try:
            album_id = data['album_id']
            logger.info(f"📸 Analyse album {album_id}")
            
            # Récupérer les services
            services = app.config.get('SERVICES', {})
            immich_service = services.get('immich_service')
            
            if not immich_service:
                raise ValueError("Service Immich non disponible")
            
            # Étape 1: Récupérer tous les assets de l'album
            sse_manager.broadcast_progress(
                request_id, 'fetch_album', 10,
                f'Récupération des images de l\'album...'
            )
            
            album_assets = immich_service.get_album_assets(album_id)
            
            if not album_assets:
                raise ValueError("Album vide ou non trouvé")
            
            sse_manager.broadcast_result(request_id, 'album_info', {
                'album_id': album_id,
                'total_assets': len(album_assets)
            })
            
            # Utiliser le process de détection avec tous les assets
            data['selected_asset_ids'] = [asset['id'] for asset in album_assets]
            
            # Continuer avec le process normal
            process_duplicate_detection_async(request_id, data, app)
            
        except Exception as e:
            logger.error(f"❌ Erreur analyse album: {e}")
            sse_manager.broadcast_error(request_id, str(e))

# Modifier la fonction _download_images_from_immich dans duplicate_routes.py pour supporter le mode test

def _download_images_from_immich(asset_ids: List[str], immich_service=None) -> List[Dict]:
    """Helper pour télécharger les images depuis Immich ou utiliser des données de test"""
    images = []
    
    # Mode test : si les asset_ids commencent par "test-"
    if asset_ids and asset_ids[0].startswith('test-'):
        logger.info("🧪 Mode test détecté - génération d'images de test")
        
        # Générer des images de test
        from PIL import Image
        import io
        
        for i, asset_id in enumerate(asset_ids):
            # Créer une image simple avec couleur différente
            colors = ['red', 'orange', 'yellow', 'green', 'blue']
            img = Image.new('RGB', (400, 300), color=colors[i % len(colors)])
            
            # Si c'est le dernier, faire un doublon du premier
            if i == len(asset_ids) - 1 and len(asset_ids) > 1:
                img = Image.new('RGB', (400, 300), color=colors[0])
            
            # Convertir en bytes
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG')
            image_data = buffer.getvalue()
            
            images.append({
                'asset_id': asset_id,
                'data': image_data,
                'filename': f'test_{i}.jpg'
            })
        
        logger.info(f"✅ {len(images)} images de test générées")
        return images
    
    # Mode normal : télécharger depuis Immich
    if not immich_service:
        logger.error("Service Immich non fourni")
        return []
    
    for asset_id in asset_ids:
        try:
            image_data = immich_service.download_asset_image(asset_id)
            if image_data:
                images.append({
                    'asset_id': asset_id,
                    'data': image_data
                })
        except Exception as e:
            logger.warning(f"Erreur téléchargement {asset_id}: {e}")
    
    return images