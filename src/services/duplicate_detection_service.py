#!/usr/bin/env python3
"""
📍 src/services/duplicate_detection_service.py

Service de détection de doublons d'images
Utilise imagehash pour comparer les images
"""

import logging
import time
import hashlib
from typing import List, Dict, Optional
from dataclasses import dataclass
from PIL import Image
import imagehash
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class DuplicateImage:
    asset_id: str
    filename: str
    date: str
    thumbnail_url: str
    similarity: float = 1.0
    is_best: bool = False
    quality_score: float = 0
    blur_score: float = 0
    file_size: int = 0
    resolution: int = 0

@dataclass
class DuplicateGroup:
    group_id: str
    images: List[DuplicateImage]
    similarity_avg: float
    
    @property
    def total_images(self):
        return len(self.images)

class DuplicateDetectionService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.stats = {
            'total_analyzed': 0,
            'duplicates_found': 0,
            'last_analysis': None
        }
    
    def analyze_selection_only(self, images_data: List[Dict], threshold: float = 0.85) -> List[DuplicateGroup]:
        """
        Analyser UNIQUEMENT les images fournies entre elles pour trouver les doublons
        
        Args:
            images_data: Liste des images à analyser (avec 'id', 'path', 'filename', etc.)
            threshold: Seuil de similarité (0-1)
        
        Returns:
            Liste des groupes de doublons trouvés
        """
        self.logger.info(f"🔍 Analyse de {len(images_data)} images sélectionnées")
        
        if len(images_data) < 2:
            return []
        
        # Calculer les hashes perceptuels pour chaque image
        image_hashes = {}
        for img_data in images_data:
            try:
                # Ouvrir l'image
                img = Image.open(img_data['path'])
                
                # Calculer plusieurs types de hash pour plus de précision
                dhash = imagehash.dhash(img)
                phash = imagehash.phash(img)
                whash = imagehash.whash(img)
                
                image_hashes[img_data['id']] = {
                    'dhash': dhash,
                    'phash': phash,
                    'whash': whash,
                    'data': img_data
                }
            except Exception as e:
                self.logger.error(f"Erreur hash pour {img_data['id']}: {e}")
        
        # Grouper les images similaires
        groups = []
        processed = set()
        
        for id1, hash1 in image_hashes.items():
            if id1 in processed:
                continue
            
            current_group = [hash1['data']]
            similarities = []
            
            for id2, hash2 in image_hashes.items():
                if id1 == id2 or id2 in processed:
                    continue
                
                # Calculer la similarité moyenne
                dhash_sim = 1 - (hash1['dhash'] - hash2['dhash']) / 64.0
                phash_sim = 1 - (hash1['phash'] - hash2['phash']) / 64.0
                whash_sim = 1 - (hash1['whash'] - hash2['whash']) / 64.0
                
                avg_similarity = (dhash_sim + phash_sim + whash_sim) / 3
                
                if avg_similarity >= threshold:
                    current_group.append(hash2['data'])
                    similarities.append(avg_similarity)
                    processed.add(id2)
            
            if len(current_group) > 1:
                processed.add(id1)
                
                group = DuplicateGroup(
                    group_id=f"group_{len(groups)+1}_{int(time.time())}",
                    images=[
                        DuplicateImage(
                            asset_id=img['id'],
                            filename=img['filename'],
                            date=img['date'],
                            thumbnail_url=img['thumbnail_url'],
                            similarity=1.0 if i == 0 else similarities[i-1]
                        )
                        for i, img in enumerate(current_group)
                    ],
                    similarity_avg=sum(similarities) / len(similarities) if similarities else 1.0
                )
                
                groups.append(group)
        
        # Mettre à jour les stats
        self.stats['total_analyzed'] += len(images_data)
        self.stats['duplicates_found'] += len(groups)
        self.stats['last_analysis'] = time.time()
        
        self.logger.info(f"✅ {len(groups)} groupes de doublons trouvés")
        return groups
    
    def determine_best_image(self, group: DuplicateGroup) -> DuplicateImage:
        """
        Déterminer la meilleure image d'un groupe basé sur plusieurs critères
        
        Critères simplifiés pour le moment (à améliorer avec analyse réelle)
        """
        best_score = -1
        best_image = group.images[0]
        
        for img in group.images:
            # Score simplifié basé sur le nom de fichier et la date
            score = 0
            
            # Préférer les noms sans "copy" ou numéro
            if 'copy' not in img.filename.lower():
                score += 10
            if not any(char.isdigit() for char in img.filename[-10:]):
                score += 5
            
            # Simuler un score de qualité aléatoire (à remplacer par analyse réelle)
            import random
            quality_score = random.randint(50, 100)
            img.quality_score = quality_score
            score += quality_score / 10
            
            if score > best_score:
                best_score = score
                best_image = img
        
        return best_image
    
    def analyze_album_for_duplicates(self, images_data: List[Dict], threshold: float = 0.85, 
                                   time_window_hours: int = 24, 
                                   progress_callback=None) -> List[DuplicateGroup]:
        """
        Analyser tout un album pour trouver les doublons
        Version complète avec fenêtre temporelle et callback de progression
        """
        # Pour l'instant, utiliser la même logique que analyze_selection_only
        # Dans une vraie implémentation, on pourrait optimiser pour les gros albums
        return self.analyze_selection_only(images_data, threshold)
    
    def get_stats(self):
        """Retourner les statistiques du service"""
        return self.stats