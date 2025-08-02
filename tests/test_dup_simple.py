#!/usr/bin/env python3
"""
Test simplifié pour la détection de doublons
"""

import os
from dotenv import load_dotenv
import requests
import json
import base64
from pathlib import Path

# Charger .env
load_dotenv()

# Configuration
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5001')
IMMICH_PROXY_URL = os.getenv('IMMICH_PROXY_URL', 'http://localhost:3001')
IMMICH_API_KEY = os.getenv('IMMICH_API_KEY', '')

# Asset IDs de test
TEST_ASSETS = [
    "f7aef515-e6b7-4d1a-bc89-e9e828e3b55e",
    "9a7475c0-a286-42bf-b02c-94246c5cf937",
    "0f5c707b-2b5b-45c0-b881-e62f6eddc06d"
]

def test_find_similar_by_ids():
    """Test 1: Envoyer juste les asset IDs"""
    print("\n🔍 TEST 1: Détection avec asset IDs")
    print("=" * 50)
    
    # Endpoint qui devrait exister dans votre API
    url = f"{SERVER_URL}/api/duplicates/find-similar"
    
    payload = {
        "asset_ids": TEST_ASSETS,
        "threshold": 0.85
    }
    
    print(f"Envoi à: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload)
        print(f"\nRéponse: HTTP {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Succès!")
            if result.get('groups'):
                print(f"Groupes trouvés: {len(result['groups'])}")
                for g in result['groups']:
                    print(f"  - Groupe: {len(g['images'])} images, similarité: {g['similarity']:.2%}")
            else:
                print("Aucun doublon trouvé")
        else:
            print(f"❌ Erreur: {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

def test_find_similar_with_manual_download():
    """Test 2: Télécharger et envoyer les images en base64"""
    print("\n📥 TEST 2: Détection avec téléchargement manuel")
    print("=" * 50)
    
    # D'abord, télécharger les images
    images_data = []
    
    for asset_id in TEST_ASSETS:
        print(f"\nTéléchargement {asset_id}...")
        
        # Utiliser l'endpoint qui marche
        url = f"{IMMICH_PROXY_URL}/api/assets/{asset_id}/thumbnail?size=preview"
        headers = {'x-api-key': IMMICH_API_KEY}
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                # Encoder en base64
                b64 = base64.b64encode(response.content).decode('utf-8')
                content_type = response.headers.get('content-type', 'image/jpeg')
                
                images_data.append({
                    "asset_id": asset_id,
                    "image_base64": f"data:{content_type};base64,{b64}"
                })
                print("✅ Image téléchargée")
            else:
                print(f"❌ Erreur téléchargement: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
    
    if len(images_data) < 2:
        print("⚠️ Pas assez d'images pour comparer")
        return
    
    # Chercher le bon endpoint
    endpoints_to_try = [
        "/api/duplicates/find-similar-with-images",
        "/api/duplicates/detect",
        "/api/duplicates/compare"
    ]
    
    payload = {
        "images": images_data,
        "threshold": 0.85
    }
    
    for endpoint in endpoints_to_try:
        url = f"{SERVER_URL}{endpoint}"
        print(f"\nEssai endpoint: {endpoint}")
        
        try:
            response = requests.post(url, json=payload)
            print(f"Réponse: HTTP {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print("✅ Endpoint trouvé!")
                # Afficher résultats...
                break
            elif response.status_code == 404:
                print("❌ Endpoint n'existe pas")
            else:
                print(f"❌ Erreur: {response.text[:100]}")
                
        except Exception as e:
            print(f"❌ Exception: {e}")

def check_available_endpoints():
    """Vérifier quels endpoints existent"""
    print("\n🔍 VÉRIFICATION DES ENDPOINTS DISPONIBLES")
    print("=" * 50)
    
    endpoints = [
        "/api/duplicates/find-similar",
        "/api/duplicates/find-similar-with-images",
        "/api/duplicates/detect",
        "/api/duplicates/analyze",
        "/api/duplicates/status"
    ]
    
    for endpoint in endpoints:
        url = f"{SERVER_URL}{endpoint}"
        try:
            # Test avec OPTIONS ou GET
            response = requests.options(url)
            if response.status_code < 500:
                print(f"✅ {endpoint} - Existe (HTTP {response.status_code})")
            else:
                print(f"❓ {endpoint} - Status {response.status_code}")
        except:
            print(f"❌ {endpoint} - Erreur connexion")

def main():
    print("🧪 Test Simplifié - Détection de Doublons")
    print("=" * 60)
    
    if not IMMICH_API_KEY:
        print("❌ IMMICH_API_KEY non configurée!")
        return
    
    # 1. Vérifier les endpoints disponibles
    check_available_endpoints()
    
    # 2. Test avec asset IDs seulement
    test_find_similar_by_ids()
    
    # 3. Test avec téléchargement manuel (si nécessaire)
    # test_find_similar_with_manual_download()
    
    print("\n✅ Tests terminés!")

if __name__ == "__main__":
    main()