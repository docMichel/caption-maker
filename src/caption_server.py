#!/usr/bin/env python3
"""
📍 src/caption_server.py

Serveur Flask principal pour génération de légendes IA
Point d'entrée de l'application
"""

from dotenv import load_dotenv
load_dotenv()  # Charge .env

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from flask_cors import CORS
import logging
import time

# Import de la configuration
from src.config.server_config import ServerConfig

# Import des blueprints
from src.api import api_bp, sse_bp, admin_bp
from src.api.duplicate_routes import duplicate_bp

# Import des services
from src.services.geo_service import GeoService
from src.services.ai_service import AIService
from src.services.immich_api_service import ImmichAPIService
from src.services.duplicate_detection_service import DuplicateDetectionService
from flask import Flask
from flask_cors import CORS
import logging
import time
import sys
from pathlib import Path

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import de la configuration
from config.server_config import ServerConfig

# Import des blueprints
from api import api_bp, sse_bp, admin_bp

# Import des services
from services.geo_service import GeoService
from services.ai_service import AIService
from services.immich_api_service import ImmichAPIService


def create_app():
    """Créer et configurer l'application Flask"""
    app = Flask(__name__)
    
    # Charger la configuration
    ServerConfig.load_from_env()
    ServerConfig.ensure_directories()
    app.config.update(ServerConfig.get_flask_config())
    
    # Activer CORS
    CORS(app)
    
    # Enregistrer les blueprints
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(sse_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/api')
    app.register_blueprint(duplicate_bp, url_prefix='/api')
    
    # Stocker le temps de démarrage
    app.config['START_TIME'] = time.time()
    # Debug : lister toutes les routes
    print("\n📍 Routes enregistrées:")
    for rule in app.url_map.iter_rules():
        print(f"   {rule.endpoint}: {rule.rule}")
    print()
    return app


def init_services(app):
    """Initialiser tous les services"""
    services = {}
    
    try:
        logger.info("🚀 Initialisation des services...")
        
        # Service de géolocalisation
        geo_service = GeoService(ServerConfig.DB_CONFIG)
        services['geo_service'] = geo_service
        logger.info("✅ GeoService initialisé")
        
        # Service IA
        ai_service = AIService(geo_service)
        services['ai_service'] = ai_service
        logger.info("✅ AIService initialisé")
        
        # Service Immich (optionnel)
        if ServerConfig.IMMICH_API_KEY:
            immich_service = ImmichAPIService(
                proxy_url=ServerConfig.IMMICH_PROXY_URL,
                api_key=ServerConfig.IMMICH_API_KEY
            )
            # Test de connexion
            connection_test = immich_service.test_connection()
            if connection_test['connected']:
                services['immich_service'] = immich_service
                logger.info("✅ ImmichAPIService connecté")
            else:
                logger.warning(f"⚠️  ImmichAPIService: {connection_test.get('error')}")
        else:
            logger.info("ℹ️  ImmichAPIService non configuré (pas de clé API)")
        

        # Service de détection de doublons
        try:
            from src.services.duplicate_detection_service import DuplicateDetectionService
            duplicate_service = DuplicateDetectionService()
            services['duplicate_service'] = duplicate_service
            logger.info("✅ DuplicateDetectionService initialisé")
        except ImportError:
            logger.warning("⚠️ DuplicateDetectionService non disponible (imagehash manquant?)")
            # Le service reste optionnel

        # Stocker les services dans la config Flask
        app.config['SERVICES'] = services
        
        logger.info("🎉 Tous les services initialisés avec succès")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur initialisation services: {e}")
        return False


def generate_ssl_certificate():
    """Générer un certificat SSL auto-signé si nécessaire"""
    cert_path = Path(ServerConfig.CERT_FILE)
    key_path = Path(ServerConfig.KEY_FILE)
    
    if not cert_path.exists() or not key_path.exists():
        print("🔐 Génération certificat SSL auto-signé...")
        import subprocess
        try:
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-out', ServerConfig.CERT_FILE, '-keyout', ServerConfig.KEY_FILE, '-days', '365',
                '-subj', '/CN=localhost'
            ], check=True)
            print("✅ Certificat SSL généré")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Impossible de générer le certificat SSL: {e}")
            print("   Continuez sans HTTPS ou générez manuellement le certificat")
            ServerConfig.USE_HTTPS = False


def print_startup_info():
    """Afficher les informations de démarrage"""
    protocol = "https" if ServerConfig.USE_HTTPS else "http"
    print("=" * 60)
    print(f"📍 Serveur: {protocol}://{ServerConfig.HOST}:{ServerConfig.PORT}")
    print(f"🔗 Health check: {protocol}://{ServerConfig.HOST}:{ServerConfig.PORT}/api/health")
    print(f"🎨 API principale: {protocol}://{ServerConfig.HOST}:{ServerConfig.PORT}/api/ai/generate-caption")
    print(f"🚀 API asynchrone: {protocol}://{ServerConfig.HOST}:{ServerConfig.PORT}/api/ai/generate-caption-async")
    print(f"⚙️  Configuration: {protocol}://{ServerConfig.HOST}:{ServerConfig.PORT}/api/ai/config")
    print(f"📊 Statistiques: {protocol}://{ServerConfig.HOST}:{ServerConfig.PORT}/api/ai/stats")
    print("=" * 60)


def main():
    """Point d'entrée principal"""
    print("🚀 Démarrage du serveur de génération de légendes")
    print("=" * 60)
    
    # Créer l'application
    app = create_app()
    
    # Générer certificat SSL si nécessaire
    if ServerConfig.USE_HTTPS:
        generate_ssl_certificate()
    
    # Initialiser les services
    if not init_services(app):
        print("❌ Échec initialisation des services")
        sys.exit(1)
    
    # Afficher les infos de démarrage
    print_startup_info()
    
    # Démarrer le serveur
    try:
        if ServerConfig.USE_HTTPS:
            import ssl
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(ServerConfig.CERT_FILE, ServerConfig.KEY_FILE)
            
            app.run(
                host=ServerConfig.HOST,
                port=ServerConfig.PORT,
                debug=ServerConfig.DEBUG,
                threaded=ServerConfig.THREADED,
                ssl_context=context
            )
        else:
            app.run(
                host=ServerConfig.HOST,
                port=ServerConfig.PORT,
                debug=ServerConfig.DEBUG,
                threaded=ServerConfig.THREADED
            )
    except KeyboardInterrupt:
        print("\n👋 Arrêt du serveur")
    except Exception as e:
        print(f"❌ Erreur démarrage serveur: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()