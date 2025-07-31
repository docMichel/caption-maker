#!/usr/bin/env python3
"""
📍 src/services/image_quality_service.py

Service d'analyse de la qualité des images
Détecte le flou, la netteté, l'exposition, etc.
"""

import cv2
import numpy as np
from PIL import Image
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ImageQualityMetrics:
    """Métriques de qualité d'une image"""
    sharpness_score: float  # 0-100, plus c'est haut, plus c'est net
    blur_score: float       # 0-100, plus c'est haut, plus c'est flou
    brightness: float       # 0-255, luminosité moyenne
    contrast: float         # 0-100, niveau de contraste
    exposure_score: float   # -100 à +100, sous/sur-exposé
    file_size: int         # Taille en bytes
    resolution: Tuple[int, int]  # (width, height)
    megapixels: float
    overall_score: float   # 0-100, score global
    
    def is_better_than(self, other: 'ImageQualityMetrics') -> bool:
        """Comparer avec une autre image"""
        return self.overall_score > other.overall_score

class ImageQualityService:
    """Service d'analyse de qualité d'image"""
    
    def __init__(self):
        self.weights = {
            'sharpness': 0.4,
            'exposure': 0.2,
            'contrast': 0.2,
            'resolution': 0.2
        }
        logger.info("🔍 ImageQualityService initialisé")
    
    def analyze_image(self, image_path: str) -> ImageQualityMetrics:
        """
        Analyser la qualité d'une image
        
        Args:
            image_path: Chemin vers l'image
            
        Returns:
            ImageQualityMetrics avec tous les scores
        """
        try:
            path = Path(image_path)
            
            # Charger l'image avec OpenCV
            img_cv = cv2.imread(str(path))
            if img_cv is None:
                raise ValueError(f"Impossible de charger l'image: {path}")
            
            # Convertir en gris pour certaines analyses
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            
            # 1. Calcul de la netteté (Laplacien)
            sharpness = self._calculate_sharpness(gray)
            blur_score = 100 - sharpness
            
            # 2. Luminosité et contraste
            brightness = np.mean(gray)
            contrast = self._calculate_contrast(gray)
            
            # 3. Score d'exposition
            exposure = self._calculate_exposure(img_cv)
            
            # 4. Résolution et taille
            height, width = img_cv.shape[:2]
            resolution = (width, height)
            megapixels = (width * height) / 1_000_000
            file_size = path.stat().st_size
            
            # 5. Score global
            overall = self._calculate_overall_score(
                sharpness, exposure, contrast, megapixels
            )
            
            return ImageQualityMetrics(
                sharpness_score=sharpness,
                blur_score=blur_score,
                brightness=brightness,
                contrast=contrast,
                exposure_score=exposure,
                file_size=file_size,
                resolution=resolution,
                megapixels=round(megapixels, 1),
                overall_score=overall
            )
            
        except Exception as e:
            logger.error(f"❌ Erreur analyse qualité: {e}")
            # Retourner des métriques par défaut
            return ImageQualityMetrics(
                sharpness_score=0,
                blur_score=100,
                brightness=128,
                contrast=50,
                exposure_score=0,
                file_size=0,
                resolution=(0, 0),
                megapixels=0,
                overall_score=0
            )
    
    def _calculate_sharpness(self, gray_image: np.ndarray) -> float:
        """
        Calculer la netteté avec la variance du Laplacien
        Plus la variance est élevée, plus l'image est nette
        """
        # Appliquer le filtre Laplacien
        laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
        variance = laplacian.var()
        
        # Normaliser sur une échelle 0-100
        # Ces valeurs sont empiriques et peuvent être ajustées
        if variance < 10:
            score = 0
        elif variance > 1000:
            score = 100
        else:
            score = (np.log10(variance) - 1) * 33.33
        
        return max(0, min(100, score))
    
    def _calculate_contrast(self, gray_image: np.ndarray) -> float:
        """Calculer le contraste (écart-type des intensités)"""
        contrast = gray_image.std()
        # Normaliser sur 0-100
        return min(100, (contrast / 64) * 100)
    
    def _calculate_exposure(self, bgr_image: np.ndarray) -> float:
        """
        Calculer le score d'exposition
        Négatif = sous-exposé, Positif = sur-exposé
        """
        # Convertir en HSV pour analyser la valeur (luminosité)
        hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
        value_channel = hsv[:, :, 2]
        
        # Calculer l'histogramme
        hist = cv2.calcHist([value_channel], [0], None, [256], [0, 256])
        hist = hist.flatten() / hist.sum()
        
        # Analyser la distribution
        # Sous-exposé: beaucoup de pixels sombres
        # Sur-exposé: beaucoup de pixels clairs
        dark_pixels = np.sum(hist[:50])
        bright_pixels = np.sum(hist[205:])
        mid_pixels = np.sum(hist[50:205])
        
        if dark_pixels > 0.5:
            # Sous-exposé
            return -50 * dark_pixels
        elif bright_pixels > 0.3:
            # Sur-exposé
            return 50 * bright_pixels
        else:
            # Bien exposé
            return 50 * mid_pixels
    
    def _calculate_overall_score(self, sharpness: float, exposure: float, 
                               contrast: float, megapixels: float) -> float:
        """Calculer un score global de qualité"""
        # Normaliser l'exposition (convertir -100/+100 en 0-100)
        exposure_normalized = 100 - abs(exposure)
        
        # Bonus pour la résolution
        resolution_score = min(100, megapixels * 10)
        
        # Calculer le score pondéré
        score = (
            sharpness * self.weights['sharpness'] +
            exposure_normalized * self.weights['exposure'] +
            contrast * self.weights['contrast'] +
            resolution_score * self.weights['resolution']
        )
        
        return round(score, 1)
    
    def compare_images(self, image_paths: list[str]) -> Dict[str, Any]:
        """
        Comparer plusieurs images et identifier la meilleure
        
        Args:
            image_paths: Liste des chemins d'images
            
        Returns:
            Dict avec l'analyse comparative
        """
        results = []
        
        for path in image_paths:
            metrics = self.analyze_image(path)
            results.append({
                'path': path,
                'filename': Path(path).name,
                'metrics': metrics
            })
        
        # Trier par score global
        results.sort(key=lambda x: x['metrics'].overall_score, reverse=True)
        
        return {
            'best_image': results[0],
            'all_results': results,
            'recommendation': self._generate_recommendation(results)
        }
    
    def _generate_recommendation(self, results: list) -> str:
        """Générer une recommandation basée sur l'analyse"""
        if len(results) < 2:
            return "Une seule image analysée"
        
        best = results[0]['metrics']
        worst = results[-1]['metrics']
        
        diff = best.overall_score - worst.overall_score
        
        if diff < 5:
            return "Toutes les images ont une qualité similaire"
        elif diff < 20:
            return f"Légère préférence pour {results[0]['filename']}"
        else:
            reasons = []
            if best.sharpness_score > worst.sharpness_score + 20:
                reasons.append("plus nette")
            if abs(best.exposure_score) < abs(worst.exposure_score) - 20:
                reasons.append("mieux exposée")
            if best.megapixels > worst.megapixels * 1.5:
                reasons.append("meilleure résolution")
            
            reason_text = " et ".join(reasons) if reasons else "meilleure qualité globale"
            return f"{results[0]['filename']} est {reason_text}"


# Tests si exécuté directement
if __name__ == "__main__":
    import sys
    
    print("🔍 Test du service de qualité d'image")
    print("=" * 50)
    
    service = ImageQualityService()
    
    if len(sys.argv) > 1:
        # Analyser les images passées en argument
        image_paths = sys.argv[1:]
        
        print(f"Analyse de {len(image_paths)} images...\n")
        
        comparison = service.compare_images(image_paths)
        
        # Afficher les résultats
        for result in comparison['all_results']:
            metrics = result['metrics']
            print(f"📸 {result['filename']}")
            print(f"   Score global: {metrics.overall_score:.1f}/100")
            print(f"   Netteté: {metrics.sharpness_score:.1f} (flou: {metrics.blur_score:.1f})")
            print(f"   Exposition: {metrics.exposure_score:+.1f}")
            print(f"   Contraste: {metrics.contrast:.1f}")
            print(f"   Résolution: {metrics.megapixels}MP")
            print()
        
        print(f"🏆 Meilleure image: {comparison['best_image']['filename']}")
        print(f"💡 {comparison['recommendation']}")
    else:
        print("Usage: python image_quality_service.py image1.jpg image2.jpg ...")