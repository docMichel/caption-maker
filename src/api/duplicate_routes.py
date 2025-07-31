#!/usr/bin/env python3
"""
📍 src/api/duplicate_routes.py

Routes API pour la détection de doublons d'images
Utilise CLIP pour comparer les embeddings visuels
"""

from flask import Blueprint, request, jsonify, Response, current_app
import logging
import json
import time
from typing import Dict, Any, List
from pathlib import Path
import tempfile

# Import du service de détection
from src.utils.image_utils import get_image_processor
from src.utils.sse_manager import get_sse_manager

logger = logging.getLogger(__name__)

# Créer le blueprint
duplicate_bp = Blueprint('duplicates', __name__)


@duplicate_bp.route('/duplicates/status', methods=['GET'])
def get_duplicate_status():
    """Vérifier le statut du service de détection de doublons"""
    try:
        # Récupérer le service depuis le contexte Flask
        duplicate_service = current_app.config.get('SERVICES', {}).get('duplicate_service')
        
        if not duplicate_service:
            return jsonify({
                'success': False,
                'clip_available': False,
                'error': 'Service de détection non initialisé'
            })
        
        stats = duplicate_service.get_stats()
        
        return jsonify({
            'success': True,
            'clip_available': duplicate_service.is_available(),
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur status duplicates: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/find-similar', methods=['POST'])
def find_similar_images():
    """Trouver les images similaires à partir d'un asset ID"""
    try:
        data = request.get_json()
        asset_id = data.get('asset_id')
        threshold = data.get('threshold', 0.85)
        time_window = data.get('time_window', 24)
        
        if not asset_id:
            return jsonify({
                'success': False,
                'error': 'asset_id requis'
            }), 400
        
        # Récupérer les services
        services = current_app.config.get('SERVICES', {})
        duplicate_service = services.get('duplicate_service')
        immich_service = services.get('immich_service')
        
        if not duplicate_service or not duplicate_service.is_available():
            return jsonify({
                'success': False,
                'error': 'Service de détection non disponible'
            }), 503
        
        # TODO: Implémenter la récupération du chemin physique de l'asset
        # Pour le moment, utiliser un chemin de test
        #source_path = f"/tmp/test_images/{asset_id}.jpg"  # À remplacer
        source_path = Path.home() / "caption-maker" / "test_images" / f"{asset_id}.jpg"
        # TODO: Récupérer les candidats depuis Immich
        # Pour le moment, utiliser des données de test
        candidates = [
            {
                'id': 'test-001',
                'filename': 'test1.jpg',
                'date': '2024-01-01T12:00:00',
                'path': '/tmp/test_images/test1.jpg',
                'thumbnail_url': f'/api/assets/test-001/thumbnail'
            }
        ]
        
        # Trouver les images similaires
        similar_images = duplicate_service.find_similar_images(
            source_path, 
            candidates,
            threshold=threshold,
            time_window_hours=time_window
        )
        
        return jsonify({
            'success': True,
            'source_asset': {
                'id': asset_id,
                'filename': 'source.jpg'  # TODO: récupérer depuis Immich
            },
            'similar_images': [img.__dict__ for img in similar_images],
            'total_found': len(similar_images)
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur find_similar: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/find-similar-from-upload', methods=['POST'])
def find_similar_from_upload():
    """Trouver les images similaires à partir d'un upload base64"""
    try:
        data = request.get_json()
        image_base64 = data.get('image_base64')
        album_id = data.get('album_id')
        threshold = data.get('threshold', 0.85)
        
        if not image_base64:
            return jsonify({
                'success': False,
                'error': 'image_base64 requise'
            }), 400
        
        # Récupérer les services
        services = current_app.config.get('SERVICES', {})
        duplicate_service = services.get('duplicate_service')
        
        if not duplicate_service or not duplicate_service.is_available():
            return jsonify({
                'success': False,
                'error': 'Service de détection non disponible'
            }), 503
        
        # Sauvegarder l'image temporairement
        image_processor = get_image_processor()
        temp_path = image_processor.save_base64_image(image_base64, "upload_test")
        
        if not temp_path:
            return jsonify({
                'success': False,
                'error': 'Erreur traitement image'
            }), 400
        
        try:
            # TODO: Récupérer les images de l'album depuis Immich
            candidates = []  # À implémenter
            
            # Trouver les similaires
            similar_images = duplicate_service.find_similar_images(
                temp_path,
                candidates,
                threshold=threshold
            )
            
            return jsonify({
                'success': True,
                'similar_images': [img.__dict__ for img in similar_images],
                'total_found': len(similar_images)
            })
            
        finally:
            # Nettoyer le fichier temporaire
            try:
                import os
                os.unlink(temp_path)
            except:
                pass
                
    except Exception as e:
        logger.error(f"❌ Erreur find_similar_upload: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/analyze-album/<album_id>', methods=['POST'])
def analyze_album_duplicates(album_id):
    """Analyser un album complet pour trouver les doublons (SSE)"""
    def generate():
        """Générateur SSE pour l'analyse"""
        sse_manager = get_sse_manager()
        
        try:
            yield f"data: {json.dumps({'event': 'start', 'data': {'album_id': album_id}})}\n\n"
            
            # Récupérer les services
            services = current_app.config.get('SERVICES', {})
            duplicate_service = services.get('duplicate_service')
            
            if not duplicate_service or not duplicate_service.is_available():
                yield f"data: {json.dumps({'event': 'error', 'data': {'error': 'Service non disponible'}})}\n\n"
                return
            
            # TODO: Récupérer les images de l'album depuis Immich
            # Pour le moment, utiliser des données de test
            images = [
                {
                    'id': f'test-{i:03d}',
                    'filename': f'test{i}.jpg',
                    'date': f'2024-01-01T{12+i}:00:00',
                    'path': f'/tmp/test_images/test{i}.jpg'
                }
                for i in range(1, 4)
            ]
            
            total = len(images)
            yield f"data: {json.dumps({'event': 'progress', 'data': {'progress': 0, 'details': f'Analyse de {total} images'}})}\n\n"
            
            # Callback pour le progress
            def progress_callback(progress, details):
                yield f"data: {json.dumps({'event': 'progress', 'data': {'progress': progress, 'details': details}})}\n\n"
            
            # Analyser l'album
            data = request.get_json() if request.is_json else {}
            threshold = data.get('threshold', 0.85)
            
            groups = duplicate_service.analyze_album_for_duplicates(
                images,
                threshold=threshold,
                progress_callback=progress_callback
            )
            
            # Convertir les groupes en dict
            groups_dict = []
            for group in groups:
                group_dict = {
                    'group_id': group.group_id,
                    'similarity_avg': group.similarity_avg,
                    'images': [img.__dict__ for img in group.images]
                }
                groups_dict.append(group_dict)
            
            # Résultat final
            yield f"data: {json.dumps({'event': 'complete', 'data': {'groups': groups_dict, 'total_groups': len(groups)}})}\n\n"
            
        except Exception as e:
            logger.error(f"❌ Erreur analyse album: {e}")
            yield f"data: {json.dumps({'event': 'error', 'data': {'error': str(e)}})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no'
    })


@duplicate_bp.route('/duplicates/create-group', methods=['POST'])
def create_duplicate_group():
    """Créer manuellement un groupe de doublons"""
    try:
        data = request.get_json()
        album_id = data.get('album_id')
        asset_ids = data.get('asset_ids', [])
        group_name = data.get('group_name', 'Manual group')
        
        if not album_id or len(asset_ids) < 2:
            return jsonify({
                'success': False,
                'error': 'album_id et au moins 2 asset_ids requis'
            }), 400
        
        # TODO: Implémenter la création de groupe dans Immich
        # Pour le moment, retourner un succès simulé
        
        return jsonify({
            'success': True,
            'group_id': f'manual_{int(time.time())}',
            'message': f'Groupe créé avec {len(asset_ids)} images'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur create_group: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/process-group', methods=['POST'])
def process_duplicate_group():
    """Traiter un groupe de doublons (garder le meilleur, fusionner, etc.)"""
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        action = data.get('action')  # keep_best, merge_metadata, delete_duplicates
        primary_asset_id = data.get('primary_asset_id')
        
        if not group_id or not action:
            return jsonify({
                'success': False,
                'error': 'group_id et action requis'
            }), 400
        
        # TODO: Implémenter les actions sur les doublons
        # - keep_best: Garder seulement l'image principale
        # - merge_metadata: Fusionner les métadonnées sur l'image principale
        # - delete_duplicates: Supprimer tous sauf le principal
        
        result = {
            'success': True,
            'action': action,
            'group_id': group_id,
            'message': f'Action {action} effectuée'
        }
        
        if action == 'keep_best':
            result['kept_asset'] = primary_asset_id
            result['deleted_count'] = 2  # Simulé
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Erreur process_group: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@duplicate_bp.route('/duplicates/stats/<album_id>', methods=['GET'])
def get_duplicate_stats(album_id):
    """Obtenir les statistiques de doublons pour un album"""
    try:
        # TODO: Implémenter avec les vraies données Immich
        # Pour le moment, retourner des stats simulées
        
        stats = {
            'success': True,
            'album_id': album_id,
            'total_images': 150,
            'duplicate_groups': 12,
            'duplicate_images': 36,
            'space_savings': '245 MB',
            'last_analysis': '2024-01-15T10:30:00'
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"❌ Erreur stats duplicates: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500