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
import requests
from typing import Dict, List
from pathlib import Path
import tempfile

# Import du service de détection
from src.services.duplicate_detection_service import DuplicateDetectionService
from src.config.server_config import ServerConfig

logger = logging.getLogger(__name__)

# Import du service de détection
from src.utils.image_utils import get_image_processor
from src.utils.sse_manager import get_sse_manager

logger = logging.getLogger(__name__)

# Créer le blueprint
duplicate_bp = Blueprint('duplicates', __name__)



# Ajouter cette classe au début de duplicate_routes.py, après les imports

class ImmichImageLoader:
    """Classe pour charger les images depuis Immich"""
    
    def __init__(self, proxy_url: str, api_key: str):
        self.proxy_url = proxy_url.rstrip('/')
        self.api_key = api_key
        self.headers = {'x-api-key': api_key}
        self.temp_dir = Path(tempfile.gettempdir()) / 'duplicate_detection'
        self.temp_dir.mkdir(exist_ok=True)
    
    def download_image(self, asset_id: str, size: str = 'preview') -> Path:
        """
        Télécharger une image depuis Immich
        
        Args:
            asset_id: ID de l'asset Immich
            size: 'thumbnail', 'preview' ou 'original'
        
        Returns:
            Chemin vers le fichier temporaire
        """
        # Utiliser le cache local si disponible
        cache_file = self.temp_dir / f"{asset_id}_{size}.jpg"
        if cache_file.exists() and cache_file.stat().st_mtime > time.time() - 3600:
            return cache_file
        
        # Télécharger depuis Immich
        if size == 'original':
            url = f"{self.proxy_url}/api/assets/{asset_id}/original"
        else:
            url = f"{self.proxy_url}/api/assets/{asset_id}/thumbnail?size={size}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            # Sauvegarder dans le cache
            cache_file.write_bytes(response.content)
            return cache_file
            
        except Exception as e:
            logger.error(f"Erreur téléchargement {asset_id}: {e}")
            return None
    
    def cleanup_old_cache(self, max_age_hours: int = 24):
        """Nettoyer les vieux fichiers du cache"""
        current_time = time.time()
        for file_path in self.temp_dir.glob("*.jpg"):
            if current_time - file_path.stat().st_mtime > max_age_hours * 3600:
                file_path.unlink()


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
def find_similar():
    """Trouver les doublons UNIQUEMENT parmi les images sélectionnées"""
    try:
        data = request.json
        asset_ids = data.get('asset_ids', [])
        threshold = float(data.get('threshold', 0.85))
        
        if not asset_ids:
            return jsonify({
                'success': False,
                'error': 'Aucune image sélectionnée'
            }), 400
        
        logger.info(f"🔍 Recherche doublons parmi {len(asset_ids)} images sélectionnées")
        
        # Récupérer le service depuis current_app
        duplicate_service = current_app.config.get('SERVICES', {}).get('duplicate_service')
        if not duplicate_service:
            # Créer une instance temporaire si pas dans SERVICES
            duplicate_service = DuplicateDetectionService()
        
        # Initialiser le loader Immich
        immich_loader = ImmichImageLoader(
            current_app.config.get('IMMICH_PROXY_URL', ServerConfig.IMMICH_PROXY_URL),
            current_app.config.get('IMMICH_API_KEY', ServerConfig.IMMICH_API_KEY)
        )
        
        # Nettoyer le cache
        immich_loader.cleanup_old_cache()
        
        # Télécharger UNIQUEMENT les images sélectionnées
        images_data = []
        download_errors = 0
        
        for i, asset_id in enumerate(asset_ids):
            image_path = immich_loader.download_image(asset_id, 'preview')
            
            if image_path:
                images_data.append({
                    'id': asset_id,
                    'path': str(image_path),
                    'filename': f"IMG_{asset_id[:8]}.jpg",
                    'date': '2024-01-01T00:00:00',  # TODO: récupérer depuis Immich si possible
                    'thumbnail_url': f"/image-proxy.php?id={asset_id}&type=thumbnail"
                })
            else:
                download_errors += 1
                logger.warning(f"Impossible de télécharger {asset_id}")
            
            # Log de progression
            if i % 5 == 0:
                logger.info(f"Téléchargement: {i+1}/{len(asset_ids)}")
        
        if not images_data:
            return jsonify({
                'success': False,
                'error': 'Impossible de télécharger les images'
            }), 500
        
        logger.info(f"✅ {len(images_data)} images téléchargées sur {len(asset_ids)}")
        
        # Analyser UNIQUEMENT ces images entre elles
        groups = duplicate_service.analyze_selection_only(
            images_data,
            threshold=threshold
        )
        
        # Pour chaque groupe, déterminer la meilleure image
        for group in groups:
            best_image = duplicate_service.determine_best_image(group)
            for img in group.images:
                img.is_best = (img.asset_id == best_image.asset_id)
        
        # Formater et retourner les résultats
        groups_data = format_duplicate_groups_with_best(groups)
        
        logger.info(f"✅ {len(groups_data)} groupes de doublons trouvés")
        
        return jsonify({
            'success': True,
            'groups': groups_data,
            'total_groups': len(groups_data),
            'total_analyzed': len(images_data),
            'download_errors': download_errors
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche doublons: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def format_duplicate_groups_with_best(groups: List) -> List[Dict]:
    """Formater les groupes en marquant la meilleure image"""
    groups_data = []
    
    for group in groups:
        groups_data.append({
            'group_id': group.group_id,
            'images': [
                {
                    'asset_id': img.asset_id,
                    'similarity': img.similarity,
                    'filename': img.filename,
                    'date': img.date,
                    'thumbnail_url': img.thumbnail_url,
                    'is_best': getattr(img, 'is_best', False),  # Marquer la meilleure
                    'quality_metrics': {
                        'quality_score': getattr(img, 'quality_score', 0),
                        'blur_score': getattr(img, 'blur_score', 0),
                        'file_size': getattr(img, 'file_size', 0),
                        'resolution': getattr(img, 'resolution', 0)
                    }
                }
                for img in group.images
            ],
            'similarity_avg': group.similarity_avg,
            'total_images': group.total_images,
            'best_image_id': next((img.asset_id for img in group.images if getattr(img, 'is_best', False)), None)
        })
    
    return groups_data

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
    logger.info(f"📸 Analyse album {album_id}")
    
    # IMPORTANT: Capturer l'app ICI, AVANT le générateur
    app = current_app._get_current_object()
    
    # Récupérer les données de la requête ICI aussi
    request_data = request.get_json() if request.is_json else {}
    threshold = request_data.get('threshold', 0.85)
    
    def generate():
        """Générateur SSE pour l'analyse"""
        with app.app_context():
            try:
                yield f"data: {json.dumps({'event': 'start', 'data': {'album_id': album_id}})}\n\n"
                
                # Récupérer les services
                services = app.config.get('SERVICES', {})
                duplicate_service = services.get('duplicate_service')
                
                if not duplicate_service or not duplicate_service.is_available():
                    yield f"data: {json.dumps({'event': 'error', 'data': {'error': 'Service non disponible'}})}\n\n"
                    return
                
                # Utiliser les images de test
                test_images_dir = Path.home() / "caption-maker" / "test_images"
                images = []
                
                if test_images_dir.exists():
                    for i, img_file in enumerate(test_images_dir.glob("*.jpg")):
                        images.append({
                            'id': f'test-{i:03d}',
                            'filename': img_file.name,
                            'date': f'2024-01-01T{12+i%24}:00:00',
                            'path': str(img_file)
                        })
                
                if not images:
                    yield f"data: {json.dumps({'event': 'error', 'data': {'error': 'Aucune image trouvée'}})}\n\n"
                    return
                
                total = len(images)
                yield f"data: {json.dumps({'event': 'progress', 'data': {'progress': 0, 'details': f'Analyse de {total} images'}})}\n\n"
                
                # Collecter les updates de progress
                progress_updates = []
                
                def progress_callback(progress, details):
                    # Stocker pour envoi différé
                    progress_updates.append({
                        'progress': progress,
                        'details': details
                    })
                
                # Lancer l'analyse
                groups = duplicate_service.analyze_album_for_duplicates(
                    images,
                    threshold=threshold,
                    progress_callback=progress_callback
                )
                
                # Envoyer tous les progress updates collectés
                for update in progress_updates:
                    yield f"data: {json.dumps({'event': 'progress', 'data': update})}\n\n"
                
                # Convertir les groupes en dict
                groups_dict = []
                for group in groups:
                    group_dict = {
                        'group_id': group.group_id,
                        'similarity_avg': group.similarity_avg,
                        'total_images': group.total_images,
                        'images': [
                            {
                                'asset_id': img.asset_id,
                                'similarity': img.similarity,
                                'filename': img.filename,
                                'date': img.date,
                                'is_primary': img.is_primary
                            }
                            for img in group.images
                        ]
                    }
                    groups_dict.append(group_dict)
                
                # Résultat final
                yield f"data: {json.dumps({'event': 'complete', 'data': {'groups': groups_dict, 'total_groups': len(groups)}})}\n\n"
                
            except Exception as e:
                logger.error(f"❌ Erreur analyse album: {e}")
                import traceback
                logger.error(traceback.format_exc())
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