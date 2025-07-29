#!/usr/bin/env python3
"""
📍 src/api/admin_routes.py

Routes API d'administration
Configuration, statistiques, maintenance
"""

from flask import Blueprint, jsonify, request
import logging
import time
from typing import Dict, Any

# Import des utilitaires
from src.utils.cache_manager import get_generation_cache
from src.utils.sse_manager import get_sse_manager
from src.utils.image_utils import get_image_processor
from src.config.server_config import ServerConfig

logger = logging.getLogger(__name__)

# Créer le blueprint
admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/ai/config', methods=['GET'])
def get_ai_config():
    """Récupérer la configuration disponible (langues, styles, modèles)"""
    try:
        # Récupérer le service IA
        from flask import current_app
        ai_service = current_app.config.get('SERVICES', {}).get('ai_service')
        
        if not ai_service:
            return jsonify({
                'success': False,
                'error': 'Service IA non disponible'
            }), 503
        
        config_info = {
            'success': True,
            'supported_options': ai_service.get_supported_options(),
            'available_models': ai_service.get_available_models(),
            'stats': ai_service.get_stats()
        }
        
        return jsonify(config_info)
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/ai/stats', methods=['GET'])
def get_stats():
    """Récupérer les statistiques d'utilisation"""
    try:
        # Récupérer les services
        from flask import current_app
        services = current_app.config.get('SERVICES', {})
        
        stats = {
            'server': {
                'uptime': time.time() - current_app.config.get('START_TIME', time.time()),
                'config': ServerConfig.summary()
            },
            'cache': get_generation_cache().get_stats(),
            'sse': get_sse_manager().get_stats()
        }
        
        # Stats des services si disponibles
        if services.get('geo_service'):
            stats['geo_service'] = services['geo_service'].get_cache_stats()
        
        if services.get('ai_service'):
            stats['ai_service'] = services['ai_service'].get_stats()
        
        if services.get('immich_service'):
            stats['immich_service'] = services['immich_service'].get_stats()
        
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/ai/clear-cache', methods=['POST'])
def clear_cache():
    """Vider tous les caches"""
    try:
        # Récupérer les services
        from flask import current_app
        services = current_app.config.get('SERVICES', {})
        
        cleared = {
            'generation_cache': 0,
            'geo_cache': 0,
            'immich_cache': 0
        }
        
        # Vider cache de génération
        cache = get_generation_cache()
        cache_size = cache.get_stats()['size']
        cache.clear()
        cleared['generation_cache'] = cache_size
        
        # Vider caches services
        if services.get('geo_service'):
            services['geo_service'].clear_cache()
            cleared['geo_cache'] = 'cleared'
        
        if services.get('immich_service'):
            services['immich_service'].clear_cache()
            cleared['immich_cache'] = 'cleared'
        
        # Nettoyer fichiers temporaires
        image_processor = get_image_processor()
        image_processor.cleanup_old_files(0)  # Tout nettoyer
        
        logger.info(f"🗑️  Caches vidés: {cleared}")
        
        return jsonify({
            'success': True,
            'message': 'Caches vidés',
            'cleared': cleared,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur vidage cache: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/ai/reload-config', methods=['POST'])
def reload_config():
    """Recharger la configuration des services"""
    try:
        # Récupérer le service IA
        from flask import current_app
        ai_service = current_app.config.get('SERVICES', {}).get('ai_service')
        
        if ai_service:
            ai_service.reload_config()
            logger.info("🔄 Configuration IA rechargée")
        
        # Recharger config serveur depuis variables d'environnement
        ServerConfig.load_from_env()
        
        return jsonify({
            'success': True,
            'message': 'Configuration rechargée',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur rechargement config: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/ai/cache/info', methods=['GET'])
def get_cache_info():
    """Obtenir des informations détaillées sur le cache"""
    try:
        cache = get_generation_cache()
        cache_info = cache.get_info()
        
        return jsonify({
            'success': True,
            'cache_info': cache_info,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur info cache: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/ai/sse/connections', methods=['GET'])
def get_sse_connections():
    """Obtenir la liste des connexions SSE actives"""
    try:
        sse_manager = get_sse_manager()
        stats = sse_manager.get_stats()
        
        return jsonify({
            'success': True,
            'connections': stats['connections_details'],
            'total_active': stats['active_connections'],
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur listing SSE: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/ai/sse/cleanup', methods=['POST'])
def cleanup_sse():
    """Nettoyer les connexions SSE inactives"""
    try:
        sse_manager = get_sse_manager()
        
        # Paramètre optionnel pour le timeout
        max_inactive = request.get_json().get('max_inactive_seconds', 300) if request.is_json else 300
        
        sse_manager.cleanup_inactive_connections(max_inactive)
        
        return jsonify({
            'success': True,
            'message': 'Connexions SSE inactives nettoyées',
            'active_connections': sse_manager.get_stats()['active_connections'],
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur nettoyage SSE: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/ai/test', methods=['POST'])
def test_pipeline():
    """Tester le pipeline complet avec une image de test"""
    try:
        # Récupérer le service IA
        from flask import current_app
        ai_service = current_app.config.get('SERVICES', {}).get('ai_service')
        
        if not ai_service:
            return jsonify({
                'success': False,
                'error': 'Service IA non disponible'
            }), 503
        
        # Image de test depuis le body ou générer une image simple
        data = request.get_json() if request.is_json else {}
        test_image_path = data.get('test_image_path')
        
        # Lancer le test
        test_result = ai_service.test_pipeline(test_image_path)
        
        return jsonify({
            'success': test_result['test_successful'],
            'test_result': test_result,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur test pipeline: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500