#!/usr/bin/env python3
"""
📍 src/services/duplicate_detection_service.py

Service de détection de doublons d'images avec CLIP
Utilise les embeddings visuels pour trouver les images similaires
"""

import logging
import hashlib
import time
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import numpy as np

# Import du service de qualité
from .image_quality_service import ImageQualityService

logger = logging.getLogger(__name__)

# Import optionnel de sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    from PIL import Image
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
    logger.warning("⚠️ sentence-transformers non installé - détection de doublons désactivée")

@dataclass
class ImageSimilarity:
    """Résultat de comparaison entre deux images"""
    asset_id: str
    similarity: float
    filename: str
    date: str
    thumbnail_url: str
    is_primary: bool = False
    quality_score: float = 0.0  # Score de qualité global
    blur_score: float = 0.0     # Score de flou (0=net, 100=flou)

@dataclass
class DuplicateGroup:
    """Groupe d'images similaires"""
    group_id: str
    images: List[ImageSimilarity]
    similarity_avg: float
    total_images: int
    
    def __post_init__(self):
        self.total_images = len(self.images)
        if self.total_images > 1:
            # Calculer la similarité moyenne
            similarities = [img.similarity for img in self.images if not img.is_primary]
            self.similarity_avg = np.mean(similarities) if similarities else 1.0

class DuplicateDetectionService:
    """Service de détection de doublons utilisant CLIP"""
    
    def __init__(self, model_name: str = 'clip-ViT-B-32', cache_dir: Optional[Path] = None):
        """
        Initialiser le service
        
        Args:
            model_name: Nom du modèle CLIP à utiliser
            cache_dir: Répertoire pour le cache des embeddings
        """
        self.model_name = model_name
        self.clip_model = None
        self.cache_dir = cache_dir or Path.home() / '.caption_generator' / 'clip_cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache des embeddings en mémoire
        self.embeddings_cache = {}
        
        # Service de qualité d'image
        self.quality_service = ImageQualityService()
        
        # Statistiques
        self.stats = {
            'total_comparisons': 0,
            'cache_hits': 0,
            'images_processed': 0,
            'groups_found': 0
        }
        
        # Initialiser CLIP si disponible
        if CLIP_AVAILABLE:
            self._init_clip()
    
    def _init_clip(self):
        """Initialiser le modèle CLIP"""
        try:
            logger.info(f"🎯 Chargement du modèle CLIP: {self.model_name}")
            self.clip_model = SentenceTransformer(self.model_name)
            logger.info(f"✅ Modèle CLIP chargé (dim: {self.clip_model.get_sentence_embedding_dimension()})")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur initialisation CLIP: {e}")
            self.clip_model = None
            return False
    
    def is_available(self) -> bool:
        """Vérifier si le service est disponible"""
        return CLIP_AVAILABLE and self.clip_model is not None
    
    def get_image_embedding(self, image_path: str) -> Optional[np.ndarray]:
        """
        Obtenir l'embedding CLIP d'une image
        
        Args:
            image_path: Chemin vers l'image
            
        Returns:
            Embedding numpy array ou None si erreur
        """
        if not self.is_available():
            return None
        
        # Générer la clé de cache
        cache_key = self._get_cache_key(image_path)
        
        # Vérifier le cache mémoire
        if cache_key in self.embeddings_cache:
            self.stats['cache_hits'] += 1
            return self.embeddings_cache[cache_key]
        
        # Vérifier le cache disque
        cache_file = self.cache_dir / f"{cache_key}.npy"
        if cache_file.exists():
            try:
                embedding = np.load(cache_file)
                self.embeddings_cache[cache_key] = embedding
                self.stats['cache_hits'] += 1
                return embedding
            except Exception as e:
                logger.warning(f"Erreur lecture cache: {e}")
        
        # Calculer l'embedding
        try:
            # Charger et préparer l'image
            image = Image.open(image_path).convert('RGB')
            
            # Encoder avec CLIP
            embedding = self.clip_model.encode(image)
            
            # Mettre en cache
            self.embeddings_cache[cache_key] = embedding
            np.save(cache_file, embedding)
            
            self.stats['images_processed'] += 1
            return embedding
            
        except Exception as e:
            logger.error(f"❌ Erreur calcul embedding pour {image_path}: {e}")
            return None
    
    def _get_cache_key(self, image_path: str) -> str:
        """Générer une clé de cache unique pour une image"""
        # Utiliser le chemin et la date de modification
        stat = os.stat(image_path)
        key_string = f"{image_path}_{stat.st_mtime}_{stat.st_size}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def find_similar_images(self, source_image_path: str, candidate_images: List[Dict],
                          threshold: float = 0.85, time_window_hours: int = 24) -> List[ImageSimilarity]:
        """
        Trouver les images similaires à une image source
        
        Args:
            source_image_path: Chemin de l'image source
            candidate_images: Liste des images candidates avec métadonnées
            threshold: Seuil de similarité (0-1)
            time_window_hours: Fenêtre temporelle pour filtrer
            
        Returns:
            Liste des images similaires triées par similarité
        """
        if not self.is_available():
            return []
        
        # Obtenir l'embedding source
        source_embedding = self.get_image_embedding(source_image_path)
        if source_embedding is None:
            return []
        
        # Date de l'image source pour filtrage temporel
        source_date = datetime.fromisoformat(candidate_images[0]['date']) if candidate_images else datetime.now()
        
        similar_images = []
        
        for candidate in candidate_images:
            # Filtrer par fenêtre temporelle
            candidate_date = datetime.fromisoformat(candidate['date'])
            time_diff = abs((candidate_date - source_date).total_seconds() / 3600)
            
            if time_diff > time_window_hours:
                continue
            
            # Obtenir l'embedding candidat
            candidate_path = candidate.get('path', '')
            if not candidate_path or not os.path.exists(candidate_path):
                continue
            
            candidate_embedding = self.get_image_embedding(candidate_path)
            if candidate_embedding is None:
                continue
            
            # Calculer la similarité
            similarity = cosine_similarity(
                source_embedding.reshape(1, -1),
                candidate_embedding.reshape(1, -1)
            )[0][0]
            
            self.stats['total_comparisons'] += 1
            
            if similarity >= threshold:
                similar_images.append(ImageSimilarity(
                    asset_id=candidate['id'],
                    similarity=float(similarity),
                    filename=candidate['filename'],
                    date=candidate['date'],
                    thumbnail_url=candidate.get('thumbnail_url', '')
                ))
        
        # Trier par similarité décroissante
        similar_images.sort(key=lambda x: x.similarity, reverse=True)
        return similar_images
    
    def analyze_album_for_duplicates(self, images: List[Dict], threshold: float = 0.85,
                                   time_window_hours: int = 24, 
                                   progress_callback=None) -> List[DuplicateGroup]:
        """
        Analyser un album complet pour trouver les groupes de doublons
        
        Args:
            images: Liste de toutes les images de l'album
            threshold: Seuil de similarité
            time_window_hours: Fenêtre temporelle
            progress_callback: Fonction callback(progress, details)
            
        Returns:
            Liste des groupes de doublons trouvés
        """
        if not self.is_available():
            return []
        
        total_images = len(images)
        logger.info(f"🔍 Analyse de {total_images} images pour doublons")
        
        # 1. Calculer tous les embeddings
        embeddings = []
        valid_indices = []
        
        for i, image in enumerate(images):
            if progress_callback:
                progress = int((i / total_images) * 50)
                progress_callback(progress, f"Encodage: {i}/{total_images}")
            
            image_path = image.get('path', '')
            if not image_path or not os.path.exists(image_path):
                embeddings.append(None)
                continue
            
            embedding = self.get_image_embedding(image_path)
            embeddings.append(embedding)
            if embedding is not None:
                valid_indices.append(i)
        
        if not valid_indices:
            logger.warning("Aucune image valide trouvée")
            return []
        
        # 2. Calculer la matrice de similarité (uniquement pour les images valides)
        if progress_callback:
            progress_callback(50, "Calcul des similarités")
        
        valid_embeddings = [embeddings[i] for i in valid_indices]
        embeddings_matrix = np.array(valid_embeddings)
        similarity_matrix = cosine_similarity(embeddings_matrix)
        
        # 3. Regrouper les images similaires
        groups = []
        processed = set()
        
        for idx, i in enumerate(valid_indices):
            if idx in processed:
                continue
            
            group_indices = [idx]
            processed.add(idx)
            
            # Trouver toutes les images similaires
            for jdx, j in enumerate(valid_indices):
                if jdx <= idx or jdx in processed:
                    continue
                
                # Vérifier similarité
                if similarity_matrix[idx][jdx] >= threshold:
                    # Vérifier proximité temporelle
                    time_diff = abs(
                        datetime.fromisoformat(images[i]['date']) - 
                        datetime.fromisoformat(images[j]['date'])
                    ).total_seconds() / 3600
                    
                    if time_diff <= time_window_hours:
                        group_indices.append(jdx)
                        processed.add(jdx)
            
            # Créer le groupe si plusieurs images
            if len(group_indices) > 1:
                group_images = []
                for k, group_idx in enumerate(group_indices):
                    real_idx = valid_indices[group_idx]
                    image = images[real_idx]
                    
                    # Calculer la similarité par rapport à la première image
                    similarity = 1.0 if k == 0 else float(similarity_matrix[group_indices[0]][group_idx])
                    
                    group_images.append(ImageSimilarity(
                        asset_id=image['id'],
                        similarity=similarity,
                        filename=image['filename'],
                        date=image['date'],
                        thumbnail_url=image.get('thumbnail_url', ''),
                        is_primary=(k == 0)
                    ))
                
                group = DuplicateGroup(
                    group_id=f"group_{len(groups)}",
                    images=group_images
                )
                groups.append(group)
            
            if progress_callback:
                progress = 50 + int((idx / len(valid_indices)) * 50)
                progress_callback(progress, f"Regroupement: {idx}/{len(valid_indices)}")
        
        self.stats['groups_found'] += len(groups)
        logger.info(f"✅ {len(groups)} groupes de doublons trouvés")
        
        return groups
    
    def calculate_space_savings(self, groups: List[DuplicateGroup], 
                              image_sizes: Dict[str, int]) -> Dict[str, Any]:
        """
        Calculer l'espace disque récupérable
        
        Args:
            groups: Groupes de doublons
            image_sizes: Tailles des images {asset_id: size_bytes}
            
        Returns:
            Statistiques d'espace
        """
        total_duplicates = 0
        total_space = 0
        
        for group in groups:
            # Toutes les images sauf la première sont des doublons
            for image in group.images[1:]:
                total_duplicates += 1
                total_space += image_sizes.get(image.asset_id, 0)
        
        return {
            'total_duplicate_images': total_duplicates,
            'total_space_bytes': total_space,
            'total_space_mb': round(total_space / (1024 * 1024), 2),
            'total_space_gb': round(total_space / (1024 * 1024 * 1024), 2)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourner les statistiques du service"""
        return {
            **self.stats,
            'clip_available': self.is_available(),
            'model_name': self.model_name,
            'cache_size': len(self.embeddings_cache),
            'embedding_dimension': self.clip_model.get_sentence_embedding_dimension() if self.clip_model else 0
        }
    
    def clear_cache(self):
        """Vider le cache des embeddings"""
        self.embeddings_cache.clear()
        
        # Optionnel: vider aussi le cache disque
        # for cache_file in self.cache_dir.glob("*.npy"):
        #     cache_file.unlink()
        
        logger.info("🗑️ Cache embeddings vidé")
    
    def _set_best_image_as_primary(self, group: DuplicateGroup):
        """
        Analyser la qualité des images du groupe et définir la meilleure comme principale
        
        Args:
            group: Groupe de doublons à analyser
        """
        if len(group.images) <= 1:
            return
        
        try:
            # Analyser la qualité de chaque image
            quality_scores = []
            
            for img in group.images:
                # Trouver le chemin de l'image
                # TODO: Adapter selon comment vous stockez les chemins
                image_path = None
                
                # Chercher dans test_images d'abord
                test_path = Path.home() / "caption-maker" / "test_images" / img.filename
                if test_path.exists():
                    image_path = str(test_path)
                
                if image_path:
                    metrics = self.quality_service.analyze_image(image_path)
                    quality_scores.append({
                        'image': img,
                        'score': metrics.overall_score,
                        'sharpness': metrics.sharpness_score,
                        'metrics': metrics
                    })
                else:
                    # Score par défaut si on ne trouve pas l'image
                    quality_scores.append({
                        'image': img,
                        'score': 50.0,
                        'sharpness': 50.0,
                        'metrics': None
                    })
            
            # Trier par score de qualité (meilleur en premier)
            quality_scores.sort(key=lambda x: (x['score'], x['sharpness']), reverse=True)
            
            # Réorganiser les images dans le groupe
            new_images = []
            for i, item in enumerate(quality_scores):
                img = item['image']
                img.is_primary = (i == 0)  # La première est la meilleure
                
                # Ajouter les infos de qualité dans les métadonnées
                if item['metrics']:
                    img.quality_score = item['score']
                    img.blur_score = item['metrics'].blur_score
                
                new_images.append(img)
            
            group.images = new_images
            
            logger.info(f"📸 Groupe {group.group_id}: Meilleure image = {new_images[0].filename} (score: {quality_scores[0]['score']:.1f})")
            
        except Exception as e:
            logger.warning(f"⚠️ Erreur analyse qualité pour groupe {group.group_id}: {e}")
            # En cas d'erreur, garder l'ordre original