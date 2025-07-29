#!/usr/bin/env python3
"""
📍 src/utils/image_utils.py

Utilitaires pour la gestion des images
Centralise le traitement base64, sauvegarde temporaire, etc.
"""

import base64
import tempfile
import logging
from pathlib import Path
import time
from typing import Optional, Tuple
# import imghdr
from PIL import Image
import io

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Gestionnaire centralisé pour le traitement des images"""
    
    def __init__(self, temp_dir: Path = None, max_size: int = 10 * 1024 * 1024):
        """
        Initialiser le processeur d'images
        
        Args:
            temp_dir: Répertoire pour fichiers temporaires
            max_size: Taille maximale en bytes
        """
        self.temp_dir = temp_dir or Path(tempfile.gettempdir()) / "caption_generator"
        self.max_size = max_size
        self.temp_dir.mkdir(exist_ok=True)
        
    def save_base64_image(self, image_base64: str, asset_id: str) -> Optional[str]:
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
            image_data = self._decode_base64(image_base64)
            
            # Vérifier la taille
            if len(image_data) > self.max_size:
                raise ValueError(f"Image trop grande: {len(image_data)} bytes (max: {self.max_size})")
            
            # Vérifier le format

            image_format = self._verify_image_format(image_data)
            if not image_format:
                raise ValueError("Format d'image non supporté")
   
            
            # Créer un fichier temporaire unique
            timestamp = int(time.time() * 1000)
            filename = f"{asset_id}_{timestamp}.{image_format}"
            temp_file = self.temp_dir / filename
            
            # Sauvegarder l'image
            with open(temp_file, 'wb') as f:
                f.write(image_data)
            
            logger.info(f"📁 Image sauvée: {temp_file.name} ({len(image_data):,} bytes)")
            return str(temp_file)
            
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde image: {e}")
            return None
    
    def _decode_base64(self, image_base64: str) -> bytes:
        """Décoder une image base64"""
        # Supprimer le préfixe data:image/xxx;base64, si présent
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]
        
        # Ajouter padding si nécessaire
        missing_padding = len(image_base64) % 4
        if missing_padding:
            image_base64 += '=' * (4 - missing_padding)
        
        return base64.b64decode(image_base64)
    
    def _verify_image_format(self, image_data: bytes) -> Optional[str]:
        """Vérifier et retourner le format de l'image"""
        # Utiliser PIL pour détecter le format
        try:
            img = Image.open(io.BytesIO(image_data))
            format_str = img.format.lower() if img.format else None
            
            # Formats supportés
            supported_formats = {'jpeg', 'jpg', 'png', 'gif', 'bmp', 'webp'}
            
            if format_str in supported_formats:
                return 'jpg' if format_str == 'jpeg' else format_str
            
            return None
        except Exception:
            return None
        
    def get_image_info(self, image_path: str) -> Optional[dict]:
        """Obtenir les informations d'une image"""
        try:
            with Image.open(image_path) as img:
                return {
                    'format': img.format,
                    'mode': img.mode,
                    'size': img.size,
                    'width': img.width,
                    'height': img.height,
                    'has_transparency': img.mode in ('RGBA', 'LA') or 
                                      (img.mode == 'P' and 'transparency' in img.info)
                }
        except Exception as e:
            logger.error(f"Erreur lecture info image: {e}")
            return None
    
    def resize_image_if_needed(self, image_path: str, max_dimension: int = 2048) -> bool:
        """
        Redimensionner l'image si elle est trop grande
        
        Args:
            image_path: Chemin de l'image
            max_dimension: Dimension maximale (largeur ou hauteur)
            
        Returns:
            True si redimensionnée, False sinon
        """
        try:
            with Image.open(image_path) as img:
                # Vérifier si redimensionnement nécessaire
                if img.width <= max_dimension and img.height <= max_dimension:
                    return False
                
                # Calculer le ratio
                ratio = min(max_dimension / img.width, max_dimension / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                
                # Redimensionner
                img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Sauvegarder (écraser l'original)
                img_resized.save(image_path, quality=90, optimize=True)
                
                logger.info(f"🖼️  Image redimensionnée: {img.size} → {new_size}")
                return True
                
        except Exception as e:
            logger.error(f"Erreur redimensionnement: {e}")
            return False
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """Nettoyer les fichiers temporaires anciens"""
        try:
            if not self.temp_dir.exists():
                return
            
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            files_deleted = 0
            
            for temp_file in self.temp_dir.glob("*"):
                if temp_file.is_file():
                    file_age = current_time - temp_file.stat().st_mtime
                    if file_age > max_age_seconds:
                        temp_file.unlink()
                        files_deleted += 1
            
            if files_deleted > 0:
                logger.info(f"🗑️  {files_deleted} fichiers temporaires supprimés")
                
        except Exception as e:
            logger.warning(f"⚠️  Erreur nettoyage fichiers: {e}")
    
    def encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """Encoder une image en base64"""
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
            
            # Détecter le type MIME avec PIL
            try:
                with Image.open(image_path) as img:
                    format_str = img.format.lower() if img.format else 'jpeg'
                    mime_type = f"image/{format_str}"
            except:
                mime_type = "image/jpeg"  # Fallback
            
            # Encoder en base64
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            # Retourner avec préfixe data URL
            return f"data:{mime_type};base64,{base64_data}"
            
        except Exception as e:
            logger.error(f"Erreur encodage base64: {e}")
            return None

# Instance globale (optionnel)
_image_processor = None

def get_image_processor(temp_dir: Path = None, max_size: int = None) -> ImageProcessor:
    """Obtenir l'instance globale du processeur d'images"""
    global _image_processor
    
    if _image_processor is None:
        from config.server_config import ServerConfig
        _image_processor = ImageProcessor(
            temp_dir=temp_dir or ServerConfig.TEMP_DIR,
            max_size=max_size or ServerConfig.MAX_IMAGE_SIZE
        )
    
    return _image_processor