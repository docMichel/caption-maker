#!/usr/bin/env python3
"""
Test de détection de doublons avec de VRAIS assets Immich
"""

import requests
import json
import time

SERVER_URL = "http://localhost:5000"
IMMICH_API_KEY = "YOUR_API_KEY"  # Remplacez par votre clé API

# REMPLACEZ CES IDs PAR DE VRAIS ASSET IDs DE VOTRE IMMICH !
REAL_ASSET_IDS = [
    "a1234567-89ab-cdef-0123-456789abcdef",  # Remplacez par un vrai ID
    "b2345678-9abc-def0-1234-56789abcdef0",  # Remplacez par un vrai ID
    "c3456789-abcd-ef01-2345-6789abcdef01",  # Remplacez par un vrai ID
]

def test_with_real_assets():
    """Test avec de vrais assets Immich"""
    
    # 1. Vérifier la connexion
    print("🔗 Test connexion serveur...")
    response = requests.get(f"{SERVER_URL}/api/health")
    if response.status_code != 200:
        print("❌ Serveur non accessible")
        return
    print("✅ Serveur OK")
    
    # 2. Test synchrone avec vrais assets
    print("\n🔍 Test détection synchrone avec vrais assets Immich...")
    
    response = requests.post(
        f"{SERVER_URL}/api/duplicates/find-similar",
        json={
            "selected_asset_ids": REAL_ASSET_IDS,
            "threshold": 0.80
        }
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Succès ! {result.get('total_groups', 0)} groupes trouvés")
        
        # Afficher les groupes
        for i, group in enumerate(result.get('groups', [])):
            print(f"\nGroupe {i+1}:")
            print(f"  Similarité: {group['similarity_