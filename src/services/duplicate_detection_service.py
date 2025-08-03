#!/usr/bin/env python3
"""
📍 src/services/duplicate_detection_service.py

Service de détection de doublons d'images utilisant CLIP
Analyse de similarité visuelle pour regrouper les images similaires
"""

import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import time
import hashlib
from PIL import Image
import io
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class DuplicateGroup:
    """Représente un groupe d'images similaires"""
    group_id: str
    images: List[Dict[str, Any]]
    similarity_avg: float
    primary_asset_id: Optional[str] = None
    
    def __post_init__(self):
        # Déterminer l'image principale si non spécifiée
        if not self.primary_asset_id and self.images:
            # Prendre la plus ancienne ou la plus grande
            self.primary_asset_id = self.images[0]['asset_id']


class DuplicateDetectionService:
    """
    Service de détection de doublons utilisant CLIP
    """
    
    def __init__(self, cache_embeddings: bool = True):
        """
        Initialiser le service
        
        Args:
            cache_embeddings: Mettre en cache les embeddings calculés
        """
        self.clip_available = False
        self.clip_model = None
        self.cache_embeddings = cache_embeddings
        self.embeddings_cache = {}
        
        # Statistiques
        self.stats = {
            'total_images_processed': 0,
            'total_groups_found': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'processing_time_total': 0.0
        }
        
        # Initialiser CLIP
        self._init_clip()
    
    def _init_clip(self):
        """Initialiser le modèle CLIP"""
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info("🚀 Chargement du modèle CLIP...")
            self.clip_model = SentenceTransformer('clip-ViT-B-32')
            self.clip_available = True
            logger.info("✅ Modèle CLIP chargé avec succès")
            
        except ImportError:
            logger.error("❌ sentence-transformers non installé")
            logger.error("   Installer avec: pip install sentence-transformers")
            
        except Exception as e:
            logger.error(f"❌ Erreur initialisation CLIP: {e}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Retourner les informations sur le modèle"""
        if not self.clip_available:
            return {'available': False, 'error': 'CLIP non disponible'}
        
        return {
            'available': True,
            'model_name': 'clip-ViT-B-32',
            'embedding_dimension': self.clip_model.get_sentence_embedding_dimension(),
            'cache_size': len(self.embeddings_cache),
            'stats': self.stats
        }
    
    def encode_image(self, image_data: bytes, asset_id: Optional[str] = None) -> Optional[np.ndarray]:
        """
        Encoder une image avec CLIP
        
        Args:
            image_data: Données binaires de l'image
            asset_id: ID pour le cache (optionnel)
            
        Returns:
            Embedding numpy array ou None si erreur
        """
        if not self.clip_available:
            logger.error("CLIP non disponible")
            return None
        
        try:
            # Vérifier le cache si asset_id fourni
            if asset_id and self.cache_embeddings:
                cache_key = self._get_cache_key(image_data, asset_id)
                if cache_key in self.embeddings_cache:
                    self.stats['cache_hits'] += 1
                    return self.embeddings_cache[cache_key]
            
            # Charger l'image
            image = Image.open(io.BytesIO(image_data)).convert('RGB')
            
            # Encoder avec CLIP
            embedding = self.clip_model.encode(image)
            
            # Mettre en cache
            if asset_id and self.cache_embeddings:
                self.embeddings_cache[cache_key] = embedding
                self.stats['cache_misses'] += 1
            
            return embedding
            
        except Exception as e:
            logger.error(f"Erreur encodage image: {e}")
            return None
    
    def encode_images_batch(self, images: List[Dict[str, Any]], 
                           batch_size: int = 10) -> List[Optional[np.ndarray]]:
        """
        Encoder plusieurs images par batch
        
        Args:
            images: Liste de dicts avec 'asset_id' et 'data'
            batch_size: Taille des batchs
            
        Returns:
            Liste des embeddings
        """
        embeddings = []
        
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            
            # Encoder chaque image du batch
            batch_embeddings = []
            for img in batch:
                embedding = self.encode_image(
                    img['data'], 
                    img.get('asset_id')
                )
                batch_embeddings.append(embedding)
            
            embeddings.extend(batch_embeddings)
            
            # Log progression
            if i % (batch_size * 5) == 0:
                logger.info(f"Encodage: {i + len(batch)}/{len(images)}")
        
        self.stats['total_images_processed'] += len(images)
        return embeddings
    
    def compute_similarity_matrix(self, embeddings: List[np.ndarray]) -> np.ndarray:
        """
        Calculer la matrice de similarité entre tous les embeddings
        
        Args:
            embeddings: Liste des embeddings
            
        Returns:
            Matrice de similarité NxN
        """
        if not embeddings:
            return np.array([])
        
        # Filtrer les None
        valid_embeddings = [e for e in embeddings if e is not None]
        
        if not valid_embeddings:
            return np.array([])
        
        # Stack en matrice
        embeddings_matrix = np.vstack(valid_embeddings)
        
        # Calculer similarité cosinus
        similarity_matrix = cosine_similarity(embeddings_matrix)
        
        return similarity_matrix
    
    def group_similar_images(self, images: List[Dict[str, Any]], 
                           similarity_matrix: np.ndarray,
                           threshold: float = 0.85,
                           time_window_hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Regrouper les images similaires
        
        Args:
            images: Liste des images avec métadonnées
            similarity_matrix: Matrice de similarité
            threshold: Seuil de similarité (0-1)
            time_window_hours: Fenêtre temporelle optionnelle
            
        Returns:
            Liste des groupes de doublons
        """
        if len(images) == 0 or similarity_matrix.size == 0:
            return []
        
        groups = []
        processed = set()
        
        for i in range(len(images)):
            if i in processed:
                continue
            
            # Nouveau groupe avec l'image i
            group_indices = [i]
            processed.add(i)
            
            # Chercher toutes les images similaires
            for j in range(i + 1, len(images)):
                if j in processed:
                    continue
                
                # Vérifier similarité
                if similarity_matrix[i][j] >= threshold:
                    # Vérifier fenêtre temporelle si demandée
                    if time_window_hours and self._check_time_proximity(
                        images[i], images[j], time_window_hours
                    ):
                        group_indices.append(j)
                        processed.add(j)
                    elif not time_window_hours:
                        group_indices.append(j)
                        processed.add(j)
            
            # Créer le groupe si plus d'une image
            if len(group_indices) > 1:
                group_images = [images[idx] for idx in group_indices]
                
                # Calculer similarité moyenne du groupe
                similarities = []
                for k in range(len(group_indices)):
                    for l in range(k + 1, len(group_indices)):
                        similarities.append(
                            similarity_matrix[group_indices[k]][group_indices[l]]
                        )
                
                avg_similarity = np.mean(similarities) if similarities else 0.0
                
                group = {
                    'group_id': f'group_{len(groups)}',
                    'images': group_images,
                    'similarity_avg': float(avg_similarity),
                    'size': len(group_images)
                }
                
                groups.append(group)
        
        self.stats['total_groups_found'] += len(groups)
        return groups
    
    def find_duplicates(self, images: List[Dict[str, Any]], 
                       threshold: float = 0.85,
                       time_window_hours: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Pipeline complet de détection de doublons
        
        Args:
            images: Liste des images avec 'asset_id' et 'data'
            threshold: Seuil de similarité
            time_window_hours: Fenêtre temporelle optionnelle
            
        Returns:
            Liste des groupes de doublons
        """
        start_time = time.time()
        
        logger.info(f"🔍 Analyse de {len(images)} images sélectionnées")
        
        # 1. Encoder toutes les images
        embeddings = self.encode_images_batch(images)
        
        # 2. Calculer la matrice de similarité
        similarity_matrix = self.compute_similarity_matrix(embeddings)
        
        # 3. Regrouper les images similaires
        groups = self.group_similar_images(
            images, similarity_matrix, threshold, time_window_hours
        )
        
        processing_time = time.time() - start_time
        self.stats['processing_time_total'] += processing_time
        
        logger.info(f"✅ {len(groups)} groupes de doublons trouvés en {processing_time:.1f}s")
        
        return groups
    
    def analyze_group_quality(self, group: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyser la qualité des images d'un groupe pour déterminer la meilleure
        
        Args:
            group: Groupe d'images similaires
            
        Returns:
            Analyse avec recommandations
        """
        images = group['images']
        analysis = {
            'group_id': group['group_id'],
            'recommendations': []
        }
        
        # Critères de sélection
        for img in images:
            score = 0
            reasons = []
            
            # Taille du fichier (plus grand = meilleure qualité)
            file_size = img.get('size', 0)
            if file_size > 0:
                size_mb = file_size / (1024 * 1024)
                score += min(size_mb / 10, 1.0)  # Normaliser sur 10MB
                reasons.append(f"Taille: {size_mb:.1f}MB")
            
            # Date (plus ancien = original probable)
            if 'date' in img:
                reasons.append(f"Date: {img['date'][:10]}")
            
            # Nom de fichier (éviter les copies)
            filename = img.get('filename', '')
            if not any(copy_indicator in filename.lower() 
                      for copy_indicator in ['copy', 'copie', '(1)', '(2)']):
                score += 0.5
                reasons.append("Nom original")
            
            img['quality_score'] = score
            img['quality_reasons'] = reasons
        
        # Trier par score
        images_sorted = sorted(images, key=lambda x: x.get('quality_score', 0), reverse=True)
        
        analysis['recommended_primary'] = images_sorted[0]['asset_id']
        analysis['quality_ranking'] = [
            {
                'asset_id': img['asset_id'],
                'filename': img.get('filename', ''),
                'score': img.get('quality_score', 0),
                'reasons': img.get('quality_reasons', [])
            }
            for img in images_sorted
        ]
        
        return analysis
    
    def _check_time_proximity(self, img1: Dict, img2: Dict, hours: int) -> bool:
        """Vérifier si deux images sont dans la fenêtre temporelle"""
        try:
            date1 = datetime.fromisoformat(img1.get('date', ''))
            date2 = datetime.fromisoformat(img2.get('date', ''))
            
            time_diff = abs((date1 - date2).total_seconds()) / 3600
            return time_diff <= hours
            
        except Exception:
            return True  # En cas d'erreur, considérer comme proche
    
    def _get_cache_key(self, image_data: bytes, asset_id: str) -> str:
        """Générer une clé de cache unique"""
        # Utiliser asset_id + hash partiel des données
        data_hash = hashlib.md5(image_data[:1024]).hexdigest()[:8]
        return f"{asset_id}_{data_hash}"
    
    def clear_cache(self):
        """Vider le cache des embeddings"""
        self.embeddings_cache.clear()
        logger.info("🗑️ Cache embeddings vidé")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourner les statistiques d'utilisation"""
        cache_hit_rate = 0
        if self.stats['cache_hits'] + self.stats['cache_misses'] > 0:
            cache_hit_rate = (
                self.stats['cache_hits'] / 
                (self.stats['cache_hits'] + self.stats['cache_misses']) * 100
            )
        
        return {
            **self.stats,
            'cache_size': len(self.embeddings_cache),
            'cache_hit_rate': f"{cache_hit_rate:.1f}%",
            'clip_available': self.clip_available
        }


# Exemple d'utilisation
if __name__ == "__main__":
    # Test du service
    print("🧪 Test DuplicateDetectionService")
    print("=" * 40)
    
    service = DuplicateDetectionService()
    
    if service.clip_available:
        print("✅ CLIP disponible")
        print(f"📊 Info modèle: {service.get_model_info()}")
    else:
        print("❌ CLIP non disponible")