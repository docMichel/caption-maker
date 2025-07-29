#!/usr/bin/env python3
"""
📍 src/utils/cache_manager.py

Gestionnaire de cache centralisé avec TTL et limite de taille
Utilisé pour éviter les régénérations inutiles
"""

import time
import hashlib
import json
import logging
from typing import Dict, Any, Optional, Tuple
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)


class CacheEntry:
    """Représente une entrée dans le cache"""
    
    def __init__(self, data: Any, ttl: int):
        self.data = data
        self.created_at = time.time()
        self.ttl = ttl
        self.access_count = 0
        self.last_accessed = self.created_at
    
    def is_valid(self) -> bool:
        """Vérifier si l'entrée est encore valide"""
        return time.time() - self.created_at < self.ttl
    
    def access(self) -> Any:
        """Accéder aux données et mettre à jour les stats"""
        self.access_count += 1
        self.last_accessed = time.time()
        return self.data


class CacheManager:
    """Gestionnaire de cache avec TTL et limite de taille"""
    
    def __init__(self, default_ttl: int = 3600, max_size: int = 100):
        """
        Initialiser le gestionnaire de cache
        
        Args:
            default_ttl: Durée de vie par défaut en secondes
            max_size: Nombre maximum d'entrées
        """
        self.default_ttl = default_ttl
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = Lock()
        
        # Statistiques
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expirations': 0
        }
    
    def generate_key(self, **kwargs) -> str:
        """
        Générer une clé de cache unique basée sur les paramètres
        
        Args:
            **kwargs: Paramètres à inclure dans la clé
            
        Returns:
            Clé de cache hashée
        """
        # Trier les clés pour consistance
        sorted_items = sorted(kwargs.items())
        key_string = json.dumps(sorted_items, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()[:16]
    
    def get(self, key: str) -> Optional[Any]:
        """
        Récupérer une valeur du cache
        
        Args:
            key: Clé de cache
            
        Returns:
            Valeur ou None si non trouvée/expirée
        """
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                
                if entry.is_valid():
                    # Hit - déplacer en fin (LRU)
                    self.cache.move_to_end(key)
                    self.stats['hits'] += 1
                    logger.debug(f"📍 Cache hit: {key}")
                    return entry.access()
                else:
                    # Expirée
                    del self.cache[key]
                    self.stats['expirations'] += 1
                    logger.debug(f"⏰ Cache expired: {key}")
            
            self.stats['misses'] += 1
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Ajouter une valeur au cache
        
        Args:
            key: Clé de cache
            value: Valeur à stocker
            ttl: TTL spécifique (optionnel)
        """
        with self.lock:
            # Si la clé existe déjà, la supprimer
            if key in self.cache:
                del self.cache[key]
            
            # Vérifier la limite de taille
            while len(self.cache) >= self.max_size:
                # Supprimer le plus ancien (LRU)
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.stats['evictions'] += 1
                logger.debug(f"🗑️ Cache eviction: {oldest_key}")
            
            # Ajouter la nouvelle entrée
            entry = CacheEntry(value, ttl or self.default_ttl)
            self.cache[key] = entry
            logger.debug(f"💾 Cache set: {key}")
    
    def delete(self, key: str) -> bool:
        """Supprimer une entrée du cache"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                logger.debug(f"🗑️ Cache delete: {key}")
                return True
            return False
    
    def clear(self):
        """Vider complètement le cache"""
        with self.lock:
            size = len(self.cache)
            self.cache.clear()
            logger.info(f"🗑️ Cache vidé ({size} entrées)")
    
    def cleanup_expired(self):
        """Nettoyer les entrées expirées"""
        with self.lock:
            expired_keys = []
            
            for key, entry in self.cache.items():
                if not entry.is_valid():
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
                self.stats['expirations'] += 1
            
            if expired_keys:
                logger.info(f"🧹 {len(expired_keys)} entrées expirées supprimées")
    
    def get_stats(self) -> Dict[str, Any]:
        """Récupérer les statistiques du cache"""
        with self.lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **self.stats,
                'size': len(self.cache),
                'max_size': self.max_size,
                'hit_rate': f"{hit_rate:.1f}%",
                'total_requests': total_requests
            }
    
    def get_info(self) -> Dict[str, Any]:
        """Récupérer des informations détaillées sur le cache"""
        with self.lock:
            entries_info = []
            current_time = time.time()
            
            for key, entry in self.cache.items():
                age = current_time - entry.created_at
                remaining_ttl = entry.ttl - age
                
                entries_info.append({
                    'key': key,
                    'age_seconds': int(age),
                    'remaining_ttl': int(max(0, remaining_ttl)),
                    'access_count': entry.access_count,
                    'is_valid': entry.is_valid()
                })
            
            return {
                'stats': self.get_stats(),
                'entries': entries_info
            }


class GenerationCache(CacheManager):
    """Cache spécialisé pour les générations de légendes"""
    
    def get_caption(self, asset_id: str, latitude: float, longitude: float, 
                   language: str, style: str) -> Optional[Dict[str, Any]]:
        """Récupérer une légende du cache"""
        key = self.generate_key(
            asset_id=asset_id,
            lat=round(latitude, 6),
            lon=round(longitude, 6),
            lang=language,
            style=style
        )
        return self.get(key)
    
    def set_caption(self, result: Dict[str, Any], asset_id: str, 
                   latitude: float, longitude: float, language: str, style: str):
        """Stocker une légende dans le cache"""
        key = self.generate_key(
            asset_id=asset_id,
            lat=round(latitude, 6),
            lon=round(longitude, 6),
            lang=language,
            style=style
        )
        self.set(key, result)


# Instance globale
_generation_cache = None

def get_generation_cache() -> GenerationCache:
    """Obtenir l'instance globale du cache de génération"""
    global _generation_cache
    if _generation_cache is None:
        from ..config.server_config import ServerConfig
        _generation_cache = GenerationCache(
            default_ttl=ServerConfig.CACHE_TTL,
            max_size=ServerConfig.CACHE_MAX_SIZE
        )
    return _generation_cache