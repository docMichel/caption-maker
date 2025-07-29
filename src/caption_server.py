#!/usr/bin/env python3
"""
📍 src/caption_server.py

Serveur Flask pour génération de légendes IA
Intégration avec l'application Immich Gallery
Support base64 pour envoi d'images entre machines
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import logging
import base64
import tempfile
import os
from pathlib import Path
import time
from typing import Dict, Any, Optional
import json
from datetime import datetime

# Import des services locaux
from services.geo_service import GeoService
from services.ai_service import AIService
from services.immich_api_service import ImmichAPIService

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration Flask
app = Flask(__name__)
CORS(app)  # Autoriser CORS pour l'intégration frontend

# Configuration globale
class Config:
    """Configuration centralisée du serveur"""
    
    # Base de données
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'root',
        'password': 'mysqlroot',
        'database': 'immich_gallery',
        'charset': 'utf8mb4'
    }
    
    # Immich API
    IMMICH_PROXY_URL = "http://localhost:3001"
    IMMICH_API_KEY = None  # À configurer
    
    # Serveur
    HOST = '127.0.0.1'
    PORT = 5000
    DEBUG = True
    
    # Limites
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_CONCURRENT_REQUESTS = 5
    CACHE_TTL = 3600  # 1 heure

# Services globaux (initialisés au démarrage)
geo_service = None
ai_service = None
immich_service = None

# Cache simple pour éviter les retraitements
generation_cache = {}
active_requests = 0

def init_services():
    """Initialiser tous les services au démarrage"""
    global geo_service, ai_service, immich_service
    
    try:
        logger.info("🚀 Initialisation des services...")
        
        # Service de géolocalisation
        geo_service = GeoService(Config.DB_CONFIG)
        logger.info("✅ GeoService initialisé")
        
        # Service IA
        ai_service = AIService(geo_service)
        logger.info("✅ AIService initialisé")
        
        # Service Immich (optionnel)
        if Config.IMMICH_API_KEY:
            immich_service = ImmichAPIService(
                proxy_url=Config.IMMICH_PROXY_URL,
                api_key=Config.IMMICH_API_KEY
            )
            # Test de connexion
            connection_test = immich_service.test_connection()
            if connection_test['connected']:
                logger.info("✅ ImmichAPIService connecté")
            else:
                logger.warning(f"⚠️  ImmichAPIService: {connection_test.get('error')}")
                immich_service = None
        else:
            logger.info("ℹ️  ImmichAPIService non configuré (pas de clé API)")
        
        logger.info("🎉 Tous les services initialisés avec succès")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur initialisation services: {e}")
        return False

def save_base64_image(image_base64: str, asset_id: str) -> Optional[str]:
    """
    Sauvegarder une image base64 temporairement
    
    Args:
        image_base64: Image encodée en base64
        asset_id: ID de l'asset pour nommage unique
        
    Returns:
        Chemin vers le fichier temporaire ou None si erreur
    """
    try:
        # Décoder le base64
        if ',' in image_base64:
            # Supprimer le préfixe data:image/xxx;base64,
            image_data = base64.b64decode(image_base64.split(',')[1])
        else:
            image_data = base64.b64decode(image_base64)
        
        # Vérifier la taille
        if len(image_data) > Config.MAX_IMAGE_SIZE:
            raise ValueError(f"Image trop grande: {len(image_data)} bytes")
        
        # Créer un fichier temporaire avec nom unique
        temp_dir = Path(tempfile.gettempdir()) / "caption_generator"
        temp_dir.mkdir(exist_ok=True)
        
        temp_file = temp_dir / f"{asset_id}_{int(time.time())}.jpg"
        
        # Sauvegarder l'image
        with open(temp_file, 'wb') as f:
            f.write(image_data)
        
        logger.info(f"📁 Image sauvée: {temp_file} ({len(image_data)} bytes)")
        return str(temp_file)
        
    except Exception as e:
        logger.error(f"❌ Erreur sauvegarde image: {e}")
        return None

def cleanup_temp_files(max_age_hours: int = 24):
    """Nettoyer les fichiers temporaires anciens"""
    try:
        temp_dir = Path(tempfile.gettempdir()) / "caption_generator"
        if not temp_dir.exists():
            return
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for temp_file in temp_dir.glob("*.jpg"):
            if current_time - temp_file.stat().st_mtime > max_age_seconds:
                temp_file.unlink()
                logger.debug(f"🗑️  Fichier temporaire supprimé: {temp_file}")
                
    except Exception as e:
        logger.warning(f"⚠️  Erreur nettoyage fichiers temporaires: {e}")

@app.route('/api/health', methods=['GET'])
def health_check():
    """Vérification santé du serveur"""
    try:
        # Vérifier les services
        services_status = {
            'geo_service': geo_service is not None,
            'ai_service': ai_service is not None,
            'immich_service': immich_service is not None
        }
        
        # Tester la base de données
        try:
            if geo_service:
                geo_service.connect_db()
                geo_service.disconnect_db()
                db_status = True
            else:
                db_status = False
        except Exception:
            db_status = False
        
        # Tester Ollama
        try:
            if ai_service:
                models_status = ai_service.get_available_models()
                ollama_status = len(models_status.get('missing', [])) == 0
            else:
                ollama_status = False
        except Exception:
            ollama_status = False
        
        status = {
            'status': 'healthy' if all(services_status.values()) else 'partial',
            'timestamp': datetime.now().isoformat(),
            'services': services_status,
            'database': db_status,
            'ollama': ollama_status,
            'active_requests': active_requests,
            'cache_size': len(generation_cache)
        }
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur health check: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/ai/generate-caption', methods=['POST'])
def generate_caption():
    """
    Endpoint principal pour génération de légendes
    
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
        if active_requests >= Config.MAX_CONCURRENT_REQUESTS:
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
        
        # Vérifier le cache
        cache_key = f"{asset_id}_{latitude}_{longitude}_{language}_{style}"
        if cache_key in generation_cache:
            cached_result, timestamp = generation_cache[cache_key]
            if time.time() - timestamp < Config.CACHE_TTL:
                logger.info(f"📍 Cache hit pour {asset_id}")
                active_requests -= 1
                return jsonify({
                    'success': True,
                    'cached': True,
                    **cached_result
                })
        
        logger.info(f"🎨 Génération légende pour asset {asset_id} ({latitude}, {longitude})")
        
        # Sauvegarder l'image temporairement
        temp_image_path = save_base64_image(image_base64, asset_id)
        if not temp_image_path:
            return jsonify({
                'success': False,
                'error': 'Erreur traitement image',
                'code': 'IMAGE_PROCESSING_ERROR'
            }), 400
        
        try:
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
            
            # Préparer la réponse détaillée
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
                
                # Contextes intermédiaires détaillés
                'intermediate_results': {
                    'image_analysis': {
                        'description': generation_result.intermediate_results.get('image_analysis_raw', {}).get('description', ''),
                        'confidence': generation_result.intermediate_results.get('image_analysis_raw', {}).get('confidence', 0),
                        'model': generation_result.intermediate_results.get('image_analysis_raw', {}).get('model_used', '')
                    },
                    'geo_context': {
                        'location_basic': generation_result.intermediate_results.get('geo_summary_basic', {}).get('location_basic', ''),
                        'cultural_context': generation_result.intermediate_results.get('geo_summary_basic', {}).get('cultural_context', ''),
                        'nearby_attractions': generation_result.intermediate_results.get('geo_summary_basic', {}).get('nearby_attractions', ''),
                        'confidence': generation_result.geo_context.get('confidence_score', 0)
                    },
                    'cultural_enrichment': generation_result.intermediate_results.get('cultural_enrichment_raw', ''),
                    'raw_caption': generation_result.intermediate_results.get('caption_raw', ''),
                    'face_context': face_context
                },
                
                # Métadonnées
                'metadata': {
                    'coordinates': [latitude, longitude],
                    'models_used': generation_result.ai_models_used,
                    'processing_steps': generation_result.processing_steps,
                    'existing_caption': existing_caption,
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            # Si il y avait une ancienne légende, l'inclure pour comparaison
            if existing_caption:
                response_data['comparison'] = {
                    'original': existing_caption,
                    'generated': generation_result.caption,
                    'improvement_suggestions': _analyze_caption_improvement(existing_caption, generation_result)
                }
            
            # Mettre en cache le résultat
            generation_cache[cache_key] = (response_data, time.time())
            
            processing_time = time.time() - request_start_time
            logger.info(f"✅ Légende générée en {processing_time:.1f}s (confiance: {generation_result.confidence_score:.2f})")
            
            return jsonify(response_data)
            
        finally:
            # Nettoyer le fichier temporaire
            try:
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

def _analyze_caption_improvement(original: str, generated_result) -> Dict[str, Any]:
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

@app.route('/api/ai/config', methods=['GET'])
def get_ai_config():
    """Récupérer la configuration disponible (langues, styles, modèles)"""
    try:
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

@app.route('/api/ai/stats', methods=['GET'])
def get_stats():
    """Récupérer les statistiques d'utilisation"""
    try:
        stats = {
            'server': {
                'uptime': time.time(),
                'active_requests': active_requests,
                'cache_size': len(generation_cache)
            }
        }
        
        if geo_service:
            stats['geo_service'] = geo_service.get_cache_stats()
        
        if ai_service:
            stats['ai_service'] = ai_service.get_stats()
        
        if immich_service:
            stats['immich_service'] = immich_service.get_stats()
        
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur récupération stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/ai/clear-cache', methods=['POST'])
def clear_cache():
    """Vider tous les caches"""
    try:
        global generation_cache
        
        # Vider cache serveur
        cache_size = len(generation_cache)
        generation_cache.clear()
        
        # Vider caches services
        if geo_service:
            geo_service.clear_cache()
        
        if immich_service:
            immich_service.clear_cache()
        
        # Nettoyer fichiers temporaires
        cleanup_temp_files(0)  # Tout nettoyer
        
        logger.info(f"🗑️  Caches vidés ({cache_size} entrées serveur)")
        
        return jsonify({
            'success': True,
            'message': f'Caches vidés ({cache_size} entrées)',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur vidage cache: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Gestionnaire d'erreurs personnalisés
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'Endpoint non trouvé',
        'code': 'NOT_FOUND'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': 'Erreur interne du serveur',
        'code': 'INTERNAL_ERROR'
    }), 500

# Nettoyage périodique des fichiers temporaires
def setup_cleanup():
    """Setup initial et nettoyage périodique"""
    cleanup_temp_files()

# Appeler setup au démarrage
with app.app_context():
    setup_cleanup()

if __name__ == "__main__":
    print("🚀 Démarrage du serveur de génération de légendes")
    print("=" * 60)
    
    # Initialiser les services
    if not init_services():
        print("❌ Échec initialisation des services")
        exit(1)
    
    # Informations de démarrage
    print(f"📍 Serveur: http://{Config.HOST}:{Config.PORT}")
    print(f"🔗 Health check: http://{Config.HOST}:{Config.PORT}/api/health")
    print(f"🎨 API principale: http://{Config.HOST}:{Config.PORT}/api/ai/generate-caption")
    print(f"⚙️  Configuration: http://{Config.HOST}:{Config.PORT}/api/ai/config")
    print("=" * 60)
    
    # Démarrer le serveur
    try:
        app.run(
            host=Config.HOST,
            port=Config.PORT,
            debug=Config.DEBUG,
            threaded=True
        )
    except KeyboardInterrupt:
        print("\n👋 Arrêt du serveur")
    except Exception as e:
        print(f"❌ Erreur démarrage serveur: {e}")