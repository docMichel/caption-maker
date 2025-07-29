#!/usr/bin/env python3
"""
📍 src/config/server_config.py

Configuration centralisée du serveur Flask
Sépare la configuration de l'implémentation
"""

from pathlib import Path
from typing import Dict, Any


class ServerConfig:
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
    IMMICH_API_KEY = None  # À configurer via env ou config locale
    
    # Configuration serveur Flask
    HOST = '0.0.0.0'  # Écouter sur toutes les interfaces
    PORT = 5000
    DEBUG = True
    THREADED = True
    
    # HTTPS (optionnel)
    USE_HTTPS = False
    CERT_FILE = 'cert.pem'
    KEY_FILE = 'key.pem'
    
    # Limites et timeouts
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_CONCURRENT_REQUESTS = 5
    REQUEST_TIMEOUT = 300  # 5 minutes
    
    # Cache
    CACHE_TTL = 3600  # 1 heure
    CACHE_MAX_SIZE = 100  # Nombre max d'entrées
    
    # Fichiers temporaires
    TEMP_DIR = Path.home() / '.caption_generator' / 'temp'
    TEMP_FILE_MAX_AGE_HOURS = 24
    
    # SSE (Server-Sent Events)
    SSE_HEARTBEAT_INTERVAL = 30  # secondes
    SSE_MESSAGE_TIMEOUT = 1.0    # timeout queue
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = 'logs/caption_server.log'
    
    @classmethod
    def load_from_env(cls):
        """Charger la configuration depuis les variables d'environnement"""
        import os
        
        # Base de données
        if os.getenv('DB_HOST'):
            cls.DB_CONFIG['host'] = os.getenv('DB_HOST')
        if os.getenv('DB_USER'):
            cls.DB_CONFIG['user'] = os.getenv('DB_USER')
        if os.getenv('DB_PASSWORD'):
            cls.DB_CONFIG['password'] = os.getenv('DB_PASSWORD')
        if os.getenv('DB_NAME'):
            cls.DB_CONFIG['database'] = os.getenv('DB_NAME')
        
        # Immich
        if os.getenv('IMMICH_PROXY_URL'):
            cls.IMMICH_PROXY_URL = os.getenv('IMMICH_PROXY_URL')
        if os.getenv('IMMICH_API_KEY'):
            cls.IMMICH_API_KEY = os.getenv('IMMICH_API_KEY')
        
        # Serveur
        if os.getenv('SERVER_HOST'):
            cls.HOST = os.getenv('SERVER_HOST')
        if os.getenv('SERVER_PORT'):
            cls.PORT = int(os.getenv('SERVER_PORT'))
        if os.getenv('SERVER_DEBUG'):
            cls.DEBUG = os.getenv('SERVER_DEBUG').lower() == 'true'
        
        # HTTPS
        if os.getenv('USE_HTTPS'):
            cls.USE_HTTPS = os.getenv('USE_HTTPS').lower() == 'true'
        
        # Cache
        if os.getenv('CACHE_TTL'):
            cls.CACHE_TTL = int(os.getenv('CACHE_TTL'))
    
    @classmethod
    def load_from_file(cls, config_file: str = 'config/local_config.json'):
        """Charger la configuration depuis un fichier JSON"""
        import json
        config_path = Path(config_file)
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Mettre à jour les attributs de classe
            for key, value in config.items():
                if hasattr(cls, key):
                    setattr(cls, key, value)
    
    @classmethod
    def get_flask_config(cls) -> Dict[str, Any]:
        """Retourner la configuration pour Flask"""
        return {
            'DEBUG': cls.DEBUG,
            'SECRET_KEY': 'dev-key-change-in-production',
            'MAX_CONTENT_LENGTH': cls.MAX_IMAGE_SIZE,
            'JSON_AS_ASCII': False,
            'JSON_SORT_KEYS': False
        }
    
    @classmethod
    def ensure_directories(cls):
        """Créer les répertoires nécessaires"""
        dirs = [
            cls.TEMP_DIR,
            Path('logs'),
            Path('data/exports'),
            Path('data/databases')
        ]
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def summary(cls) -> Dict[str, Any]:
        """Résumé de la configuration pour debug"""
        return {
            'server': {
                'host': cls.HOST,
                'port': cls.PORT,
                'debug': cls.DEBUG,
                'https': cls.USE_HTTPS
            },
            'database': {
                'host': cls.DB_CONFIG['host'],
                'database': cls.DB_CONFIG['database']
            },
            'immich': {
                'proxy_url': cls.IMMICH_PROXY_URL,
                'api_key_configured': bool(cls.IMMICH_API_KEY)
            },
            'limits': {
                'max_image_size_mb': cls.MAX_IMAGE_SIZE / 1024 / 1024,
                'max_concurrent_requests': cls.MAX_CONCURRENT_REQUESTS,
                'cache_ttl_hours': cls.CACHE_TTL / 3600
            }
        }