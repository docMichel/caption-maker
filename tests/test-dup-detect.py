#!/usr/bin/env python3
"""
📍 test_duplicates_detection.py
Script de test pour la détection de doublons avec le serveur Caption Maker
Teste différents endpoints et configurations
"""

import os
import sys
from dotenv import load_dotenv
import requests
import json
import base64
import time
from pathlib import Path
import logging

# Charger les variables d'environnement
load_dotenv()

# Configuration depuis .env ou valeurs par défaut
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5001')
IMMICH_PROXY_URL = os.getenv('IMMICH_PROXY_URL', 'http://localhost:3001')
IMMICH_API_KEY = os.getenv('IMMICH_API_KEY', '')

# Configuration logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    END = '\033[0m'

def test_immich_connection():
    """Tester la connexion directe à Immich"""
    print(f"\n{Colors.YELLOW}=== TEST CONNEXION IMMICH ==={Colors.END}")
    
    headers = {'x-api-key': IMMICH_API_KEY}
    
    # Test 1: Server info
    try:
        response = requests.get(f"{IMMICH_PROXY_URL}/api/server-info/version", headers=headers)
        if response.status_code == 200:
            print(f"{Colors.GREEN}✅ Connexion Immich OK{Colors.END}")
            print(f"Version: {response.json()}")
        else:
            print(f"{Colors.RED}❌ Erreur connexion Immich: {response.status_code}{Colors.END}")
            return False
    except Exception as e:
        print(f"{Colors.RED}❌ Impossible de contacter Immich: {e}{Colors.END}")
        return False
    
    return True

def test_asset_endpoints(asset_id):
    """Tester différents endpoints pour un asset"""
    print(f"\n{Colors.BLUE}Test endpoints pour asset: {asset_id}{Colors.END}")
    
    headers = {'x-api-key': IMMICH_API_KEY}
    
    # Endpoints à tester basés sur la doc Immich
    endpoints = [
        # Info asset
        f"/api/assets/{asset_id}",
        
        # Tailles selon la doc (thumbnail, preview, fullsize)
        f"/api/assets/{asset_id}/thumbnail",
        f"/api/assets/{asset_id}/thumbnail?size=thumbnail",
        f"/api/assets/{asset_id}/thumbnail?size=preview", 
        f"/api/assets/{asset_id}/thumbnail?size=fullsize",
        
        # Variantes possibles
        f"/api/assets/{asset_id}/preview",
        f"/api/assets/{asset_id}/fullsize",
        f"/api/assets/{asset_id}/original",
        
        # Anciens formats (au cas où)
        f"/api/asset/thumbnail/{asset_id}",
        f"/api/asset/thumbnail/{asset_id}?size=preview",
        f"/api/asset/file/{asset_id}",
        f"/api/asset/download/{asset_id}"
    ]
    
    for endpoint in endpoints:
        try:
            url = f"{IMMICH_PROXY_URL}{endpoint}"
            print(f"\nTest: {endpoint}")
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                print(f"{Colors.GREEN}✅ OK{Colors.END}")
                # Si c'est un endpoint d'info, afficher les données
                if '/api/asset/' in endpoint and 'thumbnail' not in endpoint:
                    data = response.json()
                    print(f"  Type: {data.get('type', 'N/A')}")
                    print(f"  Filename: {data.get('originalFileName', 'N/A')}")
                    print(f"  Size: {data.get('exifInfo', {}).get('fileSizeInByte', 'N/A')} bytes")
            else:
                print(f"{Colors.RED}❌ Erreur {response.status_code}{Colors.END}")
                
        except Exception as e:
            print(f"{Colors.RED}❌ Exception: {e}{Colors.END}")

def get_asset_image(asset_id, use_thumbnail=True):
    """Récupérer une image depuis Immich"""
    headers = {'x-api-key': IMMICH_API_KEY}
    
    # Essayer différents endpoints selon la doc Immich
    if use_thumbnail:
        endpoints = [
            # Formats selon la doc (thumbnail, preview, fullsize)
            f"/api/assets/{asset_id}/thumbnail?size=preview",
            f"/api/assets/{asset_id}/thumbnail?size=thumbnail",
            f"/api/assets/{asset_id}/thumbnail",
        ]
    else:
        endpoints = [
            # Pour l'image complète
            f"/api/assets/{asset_id}/thumbnail?size=fullsize",
            f"/api/assets/{asset_id}/original",
            f"/api/assets/{asset_id}/fullsize",
            f"/api/asset/file/{asset_id}",
            f"/api/asset/download/{asset_id}"
        ]
    
    for endpoint in endpoints:
        try:
            url = f"{IMMICH_PROXY_URL}{endpoint}"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Encoder en base64
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                
                # Déterminer le type MIME
                content_type = response.headers.get('content-type', 'image/jpeg')
                
                return f"data:{content_type};base64,{image_base64}"
                
        except Exception as e:
            logger.error(f"Erreur endpoint {endpoint}: {e}")
            continue
    
    return None

def test_duplicate_detection_basic():
    """Test basique de détection de doublons"""
    print(f"\n{Colors.YELLOW}=== TEST DÉTECTION DOUBLONS BASIQUE ==={Colors.END}")
    
    # Asset IDs de test
    test_assets = [
        "f7aef515-e6b7-4d1a-bc89-e9e828e3b55e",
        "9a7475c0-a286-42bf-b02c-94246c5cf937", 
        "0f5c707b-2b5b-45c0-b881-e62f6eddc06d"
    ]
    
    # D'abord, vérifier que les assets existent
    print(f"\n{Colors.MAGENTA}Vérification des assets:{Colors.END}")
    valid_assets = []
    
    for asset_id in test_assets:
        headers = {'x-api-key': IMMICH_API_KEY}
        response = requests.get(
            f"{IMMICH_PROXY_URL}/api/asset/{asset_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ {asset_id}: {data.get('originalFileName', 'N/A')}")
            valid_assets.append(asset_id)
        else:
            print(f"❌ {asset_id}: Non trouvé")
    
    if not valid_assets:
        print(f"{Colors.RED}Aucun asset valide trouvé!{Colors.END}")
        return
    
    # Test avec l'API de détection
    print(f"\n{Colors.MAGENTA}Test détection de doublons:{Colors.END}")
    
    try:
        response = requests.post(
            f"{SERVER_URL}/api/duplicates/find-similar",
            json={
                "asset_ids": valid_assets,
                "threshold": 0.85
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"{Colors.GREEN}✅ Détection réussie!{Colors.END}")
                print(f"Groupes trouvés: {len(result.get('groups', []))}")
                
                for group in result.get('groups', []):
                    print(f"\nGroupe (similarité: {group['similarity']:.2%}):")
                    for img in group['images']:
                        print(f"  - {img['asset_id']}")
            else:
                print(f"{Colors.RED}❌ Erreur: {result.get('error')}{Colors.END}")
        else:
            print(f"{Colors.RED}❌ HTTP {response.status_code}: {response.text}{Colors.END}")
            
    except Exception as e:
        print(f"{Colors.RED}❌ Exception: {e}{Colors.END}")

def test_duplicate_with_manual_images():
    """Test avec téléchargement manuel des images"""
    print(f"\n{Colors.YELLOW}=== TEST AVEC TÉLÉCHARGEMENT MANUEL ==={Colors.END}")
    
    # Asset IDs de test  
    test_assets = [
        "f7aef515-e6b7-4d1a-bc89-e9e828e3b55e",
        "9a7475c0-a286-42bf-b02c-94246c5cf937",
        "0f5c707b-2b5b-45c0-b881-e62f6eddc06d"
    ]
    
    # Télécharger les images manuellement
    images_data = []
    
    for asset_id in test_assets:
        print(f"\nTéléchargement {asset_id}...")
        
        # Essayer de récupérer l'image
        image_base64 = get_asset_image(asset_id, use_thumbnail=True)
        
        if image_base64:
            images_data.append({
                "asset_id": asset_id,
                "image_base64": image_base64
            })
            print(f"{Colors.GREEN}✅ Image récupérée{Colors.END}")
        else:
            print(f"{Colors.RED}❌ Impossible de récupérer l'image{Colors.END}")
            # Essayer avec l'image complète
            image_base64 = get_asset_image(asset_id, use_thumbnail=False)
            if image_base64:
                images_data.append({
                    "asset_id": asset_id,
                    "image_base64": image_base64
                })
                print(f"{Colors.GREEN}✅ Image complète récupérée{Colors.END}")
    
    if len(images_data) < 2:
        print(f"{Colors.RED}Pas assez d'images pour la comparaison{Colors.END}")
        return
    
    # Envoyer à l'API avec les images
    print(f"\n{Colors.MAGENTA}Envoi à l'API de détection...{Colors.END}")
    
    try:
        response = requests.post(
            f"{SERVER_URL}/api/duplicates/find-similar-with-images",
            json={
                "images": images_data,
                "threshold": 0.85
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                print(f"{Colors.GREEN}✅ Analyse réussie!{Colors.END}")
                display_results(result)
            else:
                print(f"{Colors.RED}❌ Erreur: {result.get('error')}{Colors.END}")
        else:
            print(f"{Colors.RED}❌ HTTP {response.status_code}: {response.text}{Colors.END}")
            
    except Exception as e:
        print(f"{Colors.RED}❌ Exception: {e}{Colors.END}")

def test_album_analysis():
    """Test analyse d'album complet"""
    print(f"\n{Colors.YELLOW}=== TEST ANALYSE ALBUM ==={Colors.END}")
    
    # ID d'album de test
    album_id = "test-album-001"
    
    try:
        response = requests.post(
            f"{SERVER_URL}/api/duplicates/analyze-album/{album_id}",
            json={"threshold": 0.85}
        )
        
        if response.status_code == 200:
            # Pour SSE, il faudrait stream la réponse
            print(f"{Colors.GREEN}✅ Analyse lancée{Colors.END}")
        else:
            print(f"{Colors.RED}❌ HTTP {response.status_code}{Colors.END}")
            
    except Exception as e:
        print(f"{Colors.RED}❌ Exception: {e}{Colors.END}")

def display_results(result):
    """Afficher les résultats de manière formatée"""
    groups = result.get('groups', [])
    
    if not groups:
        print("Aucun doublon trouvé")
        return
    
    print(f"\n{Colors.BLUE}📊 Résultats:{Colors.END}")
    print(f"Nombre de groupes: {len(groups)}")
    
    for i, group in enumerate(groups):
        print(f"\n{Colors.MAGENTA}Groupe {i+1}:{Colors.END}")
        print(f"  Similarité: {group['similarity']:.2%}")
        print(f"  Images:")
        
        for img in group['images']:
            print(f"    - {img['asset_id']}")
            if 'filename' in img:
                print(f"      Nom: {img['filename']}")

def test_with_local_images():
    """Test avec des images locales (pour debug)"""
    print(f"\n{Colors.YELLOW}=== TEST AVEC IMAGES LOCALES ==={Colors.END}")
    
    # Créer des images de test si elles n'existent pas
    test_files = ["test1.jpg", "test2.jpg", "test3.jpg"]
    images_data = []
    
    for i, filename in enumerate(test_files):
        if Path(filename).exists():
            with open(filename, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
                images_data.append({
                    "asset_id": f"local-{i}",
                    "image_base64": f"data:image/jpeg;base64,{image_base64}"
                })
                print(f"✅ {filename} chargé")
        else:
            print(f"⚠️  {filename} non trouvé")
    
    if len(images_data) >= 2:
        # Test avec images locales
        try:
            response = requests.post(
                f"{SERVER_URL}/api/duplicates/find-similar-with-images",
                json={
                    "images": images_data,
                    "threshold": 0.75
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"{Colors.GREEN}✅ Analyse locale réussie!{Colors.END}")
                    display_results(result)
                else:
                    print(f"{Colors.RED}❌ Erreur: {result.get('error')}{Colors.END}")
                    
        except Exception as e:
            print(f"{Colors.RED}❌ Exception: {e}{Colors.END}")

def main():
    """Tests principaux"""
    print(f"{Colors.BLUE}🧪 Test Détection de Doublons - Caption Maker{Colors.END}")
    print("=" * 60)
    
    # Afficher la configuration
    print(f"\n{Colors.YELLOW}Configuration:{Colors.END}")
    print(f"  SERVER_URL: {SERVER_URL}")
    print(f"  IMMICH_PROXY_URL: {IMMICH_PROXY_URL}")
    print(f"  IMMICH_API_KEY: {'✅ Configurée' if IMMICH_API_KEY else '❌ Non configurée'}")
    
    # Vérifier la clé API
    if not IMMICH_API_KEY:
        print(f"\n{Colors.RED}⚠️  IMMICH_API_KEY non trouvée!{Colors.END}")
        print("Vérifiez votre fichier .env")
        print("Il devrait contenir: IMMICH_API_KEY=votre-clé-ici")
        return
    
    # 1. Tester la connexion Immich
    if not test_immich_connection():
        print(f"{Colors.RED}Impossible de continuer sans connexion Immich{Colors.END}")
        return
    
    # 2. Tester les endpoints pour un asset
    print(f"\n{Colors.YELLOW}=== TEST ENDPOINTS ASSET ==={Colors.END}")
    test_asset_id = "f7aef515-e6b7-4d1a-bc89-e9e828e3b55e"
    test_asset_endpoints(test_asset_id)
    
    # 3. Test détection basique
    test_duplicate_detection_basic()
    
    # 4. Test avec téléchargement manuel
    test_duplicate_with_manual_images()
    
    # 5. Test avec images locales (optionnel)
    test_with_local_images()
    
    print(f"\n{Colors.GREEN}🎉 Tests terminés!{Colors.END}")
    
    # Afficher un résumé des problèmes potentiels
    print(f"\n{Colors.YELLOW}📋 Résumé des problèmes potentiels:{Colors.END}")
    print("1. Vérifier que l'endpoint thumbnail est correct pour votre version d'Immich")
    print("2. Vérifier que la clé API a les permissions nécessaires")
    print("3. Vérifier que le modèle CLIP est bien chargé côté serveur")
    print("4. Vérifier les logs du serveur pour plus de détails")

if __name__ == "__main__":
    main()