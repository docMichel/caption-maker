#!/usr/bin/env python3
"""
📍 src/services/duplicate_detection_service.py

Service de détection de doublons d'images utilisant CLIP
Charge le modèle à la demande et identifie la meilleure image par groupe
"""

import logging
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import time
import hashlib
from PIL import Image
import io
import gc
import threading
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class DuplicateGroup:
    """Représente un groupe d'images similaires"""
    group_id: str
    images: List[Dict[str, Any]]
    similarity_avg: float
    primary_asset_id: str
    
class DuplicateDetectionService:
    """
    Service de détection de doublons avec chargement à la demande
    """
    
    def __init__(self, cache_embeddings: bool = True, auto_unload_after: int = 300):
        """
        Args:
            cache_embeddings: Mettre en cache les embeddings
            auto_unload_after: Temps en secondes avant déchargement auto (5 min par défaut)
        """
        # État du modèle
        self.clip_available = False
        self.clip_model = None
        self.model_loaded = False
        self.model_loading = False
        self.last_used = None
        self.auto_unload_after = auto_unload_after
        self.unload_timer = None
        
        # Cache et config
        self.cache_embeddings = cache_embeddings
        self.embeddings_cache = {}
        self.device = "cuda" if self._check_cuda() else "cpu"
        
        # Service de qualité d'image
        try:
            from .image_quality_service import ImageQualityService
            self.quality_service = ImageQualityService()
        except ImportError:
            logger.warning("⚠️ ImageQualityService non disponible")
            self.quality_service = None
        
        # Statistiques
        self.stats = {
            'total_images_processed': 0,
            'total_groups_found': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'processing_time_total': 0.0,
            'model_loads': 0,
            'model_unloads': 0
        }
        
        # Tester la disponibilité de CLIP sans charger
        self._check_clip_availability()
    
    def _check_cuda(self) -> bool:
        """Vérifier la disponibilité de CUDA"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    def _check_clip_availability(self):
        """Vérifier si CLIP peut être chargé"""
        try:
            import sentence_transformers
            self.clip_available = True
            logger.info("✅ CLIP disponible (non chargé)")
        except ImportError:
            self.clip_available = False
            logger.error("❌ sentence-transformers non installé")
    
    def _load_model_if_needed(self, request_id: Optional[str] = None) -> bool:
        """Charger le modèle si nécessaire avec notifications SSE"""
        if self.model_loaded:
            self._reset_unload_timer()
            return True
        
        if self.model_loading:
            # Attendre que le chargement se termine
            timeout = 30
            start = time.time()
            while self.model_loading and (time.time() - start) < timeout:
                time.sleep(0.1)
            return self.model_loaded
        
        return self._load_model(request_id)
    
    def _load_model(self, request_id: Optional[str] = None) -> bool:
        """Charger le modèle CLIP"""
        if not self.clip_available:
            return False
        
        self.model_loading = True
        start_time = time.time()
        
        try:
            # Notification SSE si disponible
            if request_id and hasattr(self, 'sse_manager'):
                self._send_sse_progress(request_id, 'model_loading', 5, 
                                      'Chargement du modèle CLIP...')
            
            from sentence_transformers import SentenceTransformer
            
            logger.info("🚀 Chargement du modèle CLIP...")
            self.clip_model = SentenceTransformer('clip-ViT-B-32')
            
            # GPU si disponible
            if self.device == "cuda":
                self.clip_model = self.clip_model.to(self.device)
                logger.info("   GPU activé")
            
            self.model_loaded = True
            self.last_used = time.time()
            self.stats['model_loads'] += 1
            
            load_time = time.time() - start_time
            logger.info(f"✅ Modèle CLIP chargé en {load_time:.1f}s")
            
            # Notification succès
            if request_id and hasattr(self, 'sse_manager'):
                self._send_sse_result(request_id, 'model_loaded', {
                    'load_time': load_time,
                    'device': self.device
                })
            
            # Démarrer le timer de déchargement
            self._reset_unload_timer()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur chargement CLIP: {e}")
            return False
        finally:
            self.model_loading = False
    
    def _unload_model(self):
        """Décharger le modèle pour libérer la mémoire"""
        if not self.model_loaded:
            return
        
        try:
            logger.info("🗑️ Déchargement du modèle CLIP...")
            
            # Annuler le timer
            if self.unload_timer:
                self.unload_timer.cancel()
                self.unload_timer = None
            
            # Libérer le modèle
            if self.clip_model is not None:
                del self.clip_model
                self.clip_model = None
            
            # Garbage collection
            gc.collect()
            
            # Libérer mémoire GPU
            if self.device == "cuda":
                try:
                    import torch
                    torch.cuda.empty_cache()
                except:
                    pass
            
            self.model_loaded = False
            self.stats['model_unloads'] += 1
            
            logger.info("✅ Modèle CLIP déchargé")
            
        except Exception as e:
            logger.error(f"❌ Erreur déchargement: {e}")
    
    def _reset_unload_timer(self):
        """Réinitialiser le timer de déchargement automatique"""
        # Annuler l'ancien timer
        if self.unload_timer:
            self.unload_timer.cancel()
        
        # Créer nouveau timer
        self.last_used = time.time()
        self.unload_timer = threading.Timer(self.auto_unload_after, self._auto_unload)
        self.unload_timer.daemon = True
        self.unload_timer.start()
    
    def _auto_unload(self):
        """Déchargement automatique après inactivité"""
        if self.model_loaded and self.last_used:
            idle_time = time.time() - self.last_used
            if idle_time >= self.auto_unload_after:
                logger.info(f"⏰ Auto-déchargement après {idle_time:.0f}s d'inactivité")
                self._unload_model()
    
    def _send_sse_progress(self, request_id: str, step: str, progress: int, details: str):
        """Envoyer progression SSE si gestionnaire disponible"""
        if hasattr(self, 'sse_manager') and self.sse_manager:
            self.sse_manager.broadcast_progress(request_id, step, progress, details)
    
    def _send_sse_result(self, request_id: str, step: str, data: Dict):
        """Envoyer résultat SSE si gestionnaire disponible"""
        if hasattr(self, 'sse_manager') and self.sse_manager:
            self.sse_manager.broadcast_result(request_id, step, data)
    
    def set_sse_manager(self, sse_manager):
        """Définir le gestionnaire SSE pour les notifications"""
        self.sse_manager = sse_manager
    
    def get_model_info(self) -> Dict[str, Any]:
        """Retourner les informations sur le modèle"""
        info = {
            'available': self.clip_available,
            'loaded': self.model_loaded,
            'loading': self.model_loading,
            'device': self.device,
            'cache_size': len(self.embeddings_cache),
            'stats': self.stats
        }
        
        if self.model_loaded:
            info['model_name'] = 'clip-ViT-B-32'
            if self.last_used:
                info['idle_seconds'] = int(time.time() - self.last_used)
        
        return info
    
    def encode_image(self, image_data: bytes, asset_id: Optional[str] = None) -> Optional[np.ndarray]:
        """Encoder une image avec CLIP"""
        # Charger le modèle si nécessaire
        if not self._load_model_if_needed():
            return None
        
        try:
            # Vérifier le cache
            if asset_id and self.cache_embeddings:
                cache_key = self._get_cache_key(image_data, asset_id)
                if cache_key in self.embeddings_cache:
                    self.stats['cache_hits'] += 1
                    return self.embeddings_cache[cache_key]
            
            # Charger l'image
            image = Image.open(io.BytesIO(image_data)).convert('RGB')
            
            # Encoder
            embedding = self.clip_model.encode(image)
            
            # Mettre en cache
            if asset_id and self.cache_embeddings:
                self.embeddings_cache[cache_key] = embedding
                self.stats['cache_misses'] += 1
            
            return embedding
            
        except Exception as e:
            logger.error(f"Erreur encodage image: {e}")
            return None
    
    def find_duplicates(self, images: List[Dict[str, Any]], 
                       threshold: float = 0.85,
                       time_window_hours: Optional[int] = None,
                       request_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Pipeline complet avec identification de la meilleure image
        
        Returns:
            Liste des groupes avec is_primary marqué
        """
        start_time = time.time()
        
        logger.info(f"🔍 Analyse de {len(images)} images")
        
        # Charger le modèle
        if not self._load_model_if_needed(request_id):
            logger.error("Impossible de charger CLIP")
            return []
        
        # 1. Encoder toutes les images
        if request_id:
            self._send_sse_progress(request_id, 'encoding', 10, 
                                  f'Encodage de {len(images)} images...')
        
        embeddings = self.encode_images_batch(images, request_id)
        
        # 2. Calculer la matrice de similarité
        if request_id:
            self._send_sse_progress(request_id, 'similarity', 40, 
                                  'Calcul des similarités...')
        
        similarity_matrix = self.compute_similarity_matrix(embeddings)
        
        # 3. Regrouper les images similaires
        if request_id:
            self._send_sse_progress(request_id, 'grouping', 60, 
                                  'Regroupement des doublons...')
        
        groups = self.group_similar_images(
            images, similarity_matrix, threshold, time_window_hours
        )
        
        # 4. Analyser la qualité et marquer la meilleure image
        if request_id:
            self._send_sse_progress(request_id, 'quality', 80, 
                                  'Analyse de la qualité...')
        
        groups_with_quality = self._analyze_groups_quality(groups, images)
        
        processing_time = time.time() - start_time
        self.stats['processing_time_total'] += processing_time
        
        logger.info(f"✅ {len(groups)} groupes trouvés en {processing_time:.1f}s")
        
        return groups_with_quality
    
    def _analyze_groups_quality(self, groups: List[Dict], 
                               all_images: List[Dict]) -> List[Dict]:
        """Analyser la qualité dans chaque groupe et marquer la meilleure"""
        if not self.quality_service:
            # Sans service qualité, prendre la première image
            for group in groups:
                for i, img in enumerate(group['images']):
                    img['is_primary'] = (i == 0)
                    img['quality_score'] = 0
                    img['quality_reasons'] = []
            return groups
        
        # Créer un mapping asset_id -> image_data pour l'analyse
        image_data_map = {img['asset_id']: img.get('data') for img in all_images}
        
        for group in groups:
            quality_scores = []
            
            # Analyser chaque image du groupe
            for img in group['images']:
                asset_id = img['asset_id']
                image_data = image_data_map.get(asset_id)
                
                if image_data:
                    # Sauvegarder temporairement pour analyse
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        tmp.write(image_data)
                        tmp_path = tmp.name
                    
                    try:
                        # Analyser la qualité
                        metrics = self.quality_service.analyze_image(tmp_path)
                        
                        img['quality_score'] = metrics.overall_score
                        img['quality_metrics'] = {
                            'sharpness': metrics.sharpness_score,
                            'exposure': metrics.exposure_score,
                            'contrast': metrics.contrast,
                            'resolution': f"{metrics.resolution[0]}x{metrics.resolution[1]}",
                            'megapixels': metrics.megapixels
                        }
                        
                        # Raisons de la qualité
                        reasons = []
                        if metrics.sharpness_score > 70:
                            reasons.append("Image nette")
                        if abs(metrics.exposure_score) < 20:
                            reasons.append("Bien exposée")
                        if metrics.megapixels > 3:
                            reasons.append(f"{metrics.megapixels}MP")
                        
                        img['quality_reasons'] = reasons
                        quality_scores.append((img, metrics.overall_score))
                        
                    except Exception as e:
                        logger.warning(f"Erreur analyse qualité {asset_id}: {e}")
                        img['quality_score'] = 0
                        img['quality_reasons'] = []
                        quality_scores.append((img, 0))
                    finally:
                        # Nettoyer le fichier temporaire
                        try:
                            import os
                            os.unlink(tmp_path)
                        except:
                            pass
                else:
                    img['quality_score'] = 0
                    img['quality_reasons'] = []
                    quality_scores.append((img, 0))
            
            # Trier par score et marquer la meilleure
            quality_scores.sort(key=lambda x: x[1], reverse=True)
            
            for i, (img, score) in enumerate(quality_scores):
                img['is_primary'] = (i == 0)
                img['quality_rank'] = i + 1
            
            # Mettre à jour l'ordre dans le groupe
            group['images'] = [img for img, _ in quality_scores]
            
            # Ajouter un résumé qualité au groupe
            if quality_scores:
                best_img, best_score = quality_scores[0]
                group['primary_asset_id'] = best_img['asset_id']
                group['quality_summary'] = {
                    'best_score': best_score,
                    'score_range': [quality_scores[-1][1], best_score]
                }
        
        return groups
    
    def encode_images_batch(self, images: List[Dict[str, Any]], 
                           request_id: Optional[str] = None) -> List[Optional[np.ndarray]]:
        """Encoder plusieurs images par batch avec progression"""
        embeddings = []
        batch_size = 10
        
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            
            # Progress SSE
            if request_id:
                progress = 10 + int((i / len(images)) * 25)  # 10-35%
                self._send_sse_progress(request_id, 'encoding', progress,
                                      f'Encodage: {i + len(batch)}/{len(images)}')
            
            # Encoder chaque image
            for img in batch:
                embedding = self.encode_image(img['data'], img.get('asset_id'))
                embeddings.append(embedding)
            
            # Log progression
            if i % (batch_size * 5) == 0:
                logger.info(f"Encodage: {i + len(batch)}/{len(images)}")
        
        self.stats['total_images_processed'] += len(images)
        return embeddings
    
    def compute_similarity_matrix(self, embeddings: List[np.ndarray]) -> np.ndarray:
        """Calculer la matrice de similarité"""
        if not embeddings:
            return np.array([])
        
        valid_embeddings = [e for e in embeddings if e is not None]
        if not valid_embeddings:
            return np.array([])
        
        embeddings_matrix = np.vstack(valid_embeddings)
        return cosine_similarity(embeddings_matrix)
    
    def group_similar_images(self, images: List[Dict[str, Any]], 
                           similarity_matrix: np.ndarray,
                           threshold: float = 0.85,
                           time_window_hours: Optional[int] = None) -> List[Dict]:
        """Regrouper les images similaires"""
        if len(images) == 0 or similarity_matrix.size == 0:
            return []
        
        groups = []
        processed = set()
        
        for i in range(len(images)):
            if i in processed:
                continue
            
            group_indices = [i]
            processed.add(i)
            
            # Chercher images similaires
            for j in range(i + 1, len(images)):
                if j in processed:
                    continue
                
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
                
                # Calculer similarité moyenne
                similarities = []
                for k in range(len(group_indices)):
                    for l in range(k + 1, len(group_indices)):
                        similarities.append(
                            similarity_matrix[group_indices[k]][group_indices[l]]
                        )
                
                avg_similarity = np.mean(similarities) if similarities else 0.0
                
                # Nettoyer les données binaires avant retour
                for img in group_images:
                    if 'data' in img:
                        del img['data']
                
                group = {
                    'group_id': f'group_{len(groups)}',
                    'images': group_images,
                    'similarity_avg': float(avg_similarity),
                    'size': len(group_images)
                }
                
                groups.append(group)
        
        self.stats['total_groups_found'] += len(groups)
        return groups
    
    def _check_time_proximity(self, img1: Dict, img2: Dict, hours: int) -> bool:
        """Vérifier si deux images sont dans la fenêtre temporelle"""
        try:
            date1 = datetime.fromisoformat(img1.get('date', ''))
            date2 = datetime.fromisoformat(img2.get('date', ''))
            
            time_diff = abs((date1 - date2).total_seconds()) / 3600
            return time_diff <= hours
            
        except Exception:
            return True
    
    def _get_cache_key(self, image_data: bytes, asset_id: str) -> str:
        """Générer une clé de cache unique"""
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
        
        stats = {
            **self.stats,
            'cache_size': len(self.embeddings_cache),
            'cache_hit_rate': f"{cache_hit_rate:.1f}%",
            'clip_available': self.clip_available,
            'model_loaded': self.model_loaded,
            'auto_unload_seconds': self.auto_unload_after
        }
        
        if self.last_used and self.model_loaded:
            stats['idle_time'] = int(time.time() - self.last_used)
        
        return stats