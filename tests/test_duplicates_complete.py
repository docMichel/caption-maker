#!/usr/bin/env python3
"""
📍 test_duplicates_immich_real.py
Test de détection de doublons avec de VRAIS assets Immich
Récupère automatiquement des assets depuis votre instance
"""

import requests
import json
import time
import os
from dotenv import load_dotenv
from datetime import datetime

# Charger les variables d'environnement
load_dotenv()

# Configuration depuis .env
CAPTION_SERVER_URL = "http://localhost:5000"
IMMICH_PROXY_URL = os.getenv('IMMICH_API_URL', 'http://localhost:3001')
IMMICH_API_KEY = os.getenv('IMMICH_API_KEY')

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'


def get_immich_assets(limit=20):
    """Récupérer des assets depuis Immich"""
    print(f"\n{Colors.CYAN}📥 Récupération d'assets depuis Immich...{Colors.END}")
    
    headers = {
        'x-api-key': IMMICH_API_KEY,  # Minuscule !
        'Content-Type': 'application/json'
    }
    
    try:
        # Pour récupérer des assets, on peut utiliser la recherche ou récupérer des albums
        # Option 1: Récupérer les albums et prendre des assets dedans
        print("  Tentative via albums...")
        albums_url = f"{IMMICH_PROXY_URL}/api/album"
        response = requests.get(albums_url, headers=headers)
        
        if response.status_code == 200:
            albums = response.json()
            if albums and isinstance(albums, list):
                print(f"  → {len(albums)} albums trouvés")
                
                # Prendre des assets du premier album non vide
                for album in albums[:3]:  # Essayer les 3 premiers albums
                    album_id = album.get('id')
                    if album_id:
                        # Récupérer les détails de l'album
                        album_detail_url = f"{IMMICH_PROXY_URL}/api/album/{album_id}"
                        album_response = requests.get(album_detail_url, headers=headers)
                        
                        if album_response.status_code == 200:
                            album_data = album_response.json()
                            assets = album_data.get('assets', [])
                            
                            if assets:
                                print(f"{Colors.GREEN}✅ {len(assets)} assets trouvés dans l'album '{album.get('albumName', 'Sans nom')}'{Colors.END}")
                                return assets[:limit]
        
        # Option 2: Si pas d'albums, essayer une recherche
        print("  Tentative via recherche...")
        search_url = f"{IMMICH_PROXY_URL}/api/search"
        search_data = {
            "q": "*",  # Recherche tout
            "type": "IMAGE",
            "page": 1,
            "size": limit
        }
        
        response = requests.post(search_url, headers=headers, json=search_data)
        
        if response.status_code == 200:
            search_results = response.json()
            assets = search_results.get('assets', {}).get('items', [])
            
            if assets:
                print(f"{Colors.GREEN}✅ {len(assets)} assets trouvés via recherche{Colors.END}")
                return assets[:limit]
        
        print(f"{Colors.YELLOW}⚠️  Aucun asset trouvé. Assurez-vous d'avoir des photos dans Immich.{Colors.END}")
        return []
        
    except Exception as e:
        print(f"{Colors.RED}❌ Erreur récupération assets: {e}{Colors.END}")
        return []


def test_duplicates_detection():
    """Test principal de détection de doublons"""
    print(f"{Colors.MAGENTA}🧪 Test Détection de Doublons - Assets Immich Réels{Colors.END}")
    print("=" * 60)
    
    # 1. Vérifier la configuration
    if not IMMICH_API_KEY:
        print(f"{Colors.RED}❌ IMMICH_API_KEY non configurée dans .env{Colors.END}")
        return
    
    print(f"📍 Serveur Caption: {CAPTION_SERVER_URL}")
    print(f"📍 Proxy Immich: {IMMICH_PROXY_URL}")
    print(f"🔑 API Key: {'✓' if IMMICH_API_KEY else '✗'}")
    
    # 2. Health check serveur
    print(f"\n{Colors.YELLOW}=== HEALTH CHECK ==={Colors.END}")
    
    try:
        response = requests.get(f"{CAPTION_SERVER_URL}/api/health")
        if response.status_code != 200:
            print(f"{Colors.RED}❌ Serveur non accessible{Colors.END}")
            return
        
        health = response.json()
        print(f"{Colors.GREEN}✅ Serveur OK{Colors.END}")
        print(f"  • Statut: {health.get('status')}")
        print(f"  • Services: {health.get('services', {})}")
        
    except Exception as e:
        print(f"{Colors.RED}❌ Erreur connexion serveur: {e}{Colors.END}")
        return
    
    # 3. Récupérer des vrais assets Immich
    assets = get_immich_assets(limit=10)
    
    if not assets:
        print(f"{Colors.RED}❌ Aucun asset trouvé dans Immich{Colors.END}")
        return
    
    # Extraire les IDs
    asset_ids = []
    for asset in assets:
        asset_id = asset.get('id') or asset.get('assetId')
        if asset_id:
            asset_ids.append(asset_id)
    
    print(f"\n{Colors.CYAN}Assets sélectionnés:{Colors.END}")
    for i, asset in enumerate(assets[:5]):  # Afficher les 5 premiers
        filename = asset.get('originalFileName', 'N/A')
        date = asset.get('fileCreatedAt', '')[:10]
        print(f"  {i+1}. {filename} ({date})")
    
    # 4. Test synchrone avec peu d'assets
    print(f"\n{Colors.YELLOW}=== TEST SYNCHRONE (3 assets) ==={Colors.END}")
    
    small_batch = asset_ids[:3]
    
    try:
        response = requests.post(
            f"{CAPTION_SERVER_URL}/api/duplicates/find-similar",
            json={
                "selected_asset_ids": small_batch,
                "threshold": 0.85
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"{Colors.GREEN}✅ Succès!{Colors.END}")
            print(f"  • Groupes trouvés: {result.get('total_groups', 0)}")
            
            # Afficher les groupes
            for group in result.get('groups', []):
                print(f"\n  Groupe (similarité {group['similarity_avg']:.1%}):")
                for img in group['images']:
                    print(f"    - {img.get('filename', img['asset_id'])}")
        else:
            print(f"{Colors.RED}❌ Erreur: {response.status_code}{Colors.END}")
            print(response.json())
            
    except Exception as e:
        print(f"{Colors.RED}❌ Erreur test synchrone: {e}{Colors.END}")
    
    # 5. Test asynchrone avec plus d'assets
    print(f"\n{Colors.YELLOW}=== TEST ASYNCHRONE SSE ({len(asset_ids)} assets) ==={Colors.END}")
    
    request_id = f"test-immich-{int(time.time())}"
    
    try:
        # Démarrer la détection async
        response = requests.post(
            f"{CAPTION_SERVER_URL}/api/duplicates/find-similar-async",
            json={
                "request_id": request_id,
                "selected_asset_ids": asset_ids,
                "threshold": 0.80,
                "group_by_time": True,
                "time_window_hours": 24
            }
        )
        
        if response.status_code == 200:
            print(f"{Colors.GREEN}✅ Détection démarrée{Colors.END}")
            print(f"Request ID: {request_id}")
            
            # Écouter le flux SSE
            listen_sse_with_timeout(request_id, timeout=60)
            
        else:
            print(f"{Colors.RED}❌ Erreur démarrage: {response.status_code}{Colors.END}")
            print(response.json())
            
    except Exception as e:
        print(f"{Colors.RED}❌ Erreur test async: {e}{Colors.END}")
    
    # 6. Test avec différents seuils
    print(f"\n{Colors.YELLOW}=== TEST SEUILS VARIÉS ==={Colors.END}")
    
    thresholds = [0.95, 0.85, 0.70]
    test_batch = asset_ids[:5]  # Utiliser 5 assets
    
    for threshold in thresholds:
        print(f"\n{Colors.CYAN}Seuil {threshold:.0%}:{Colors.END}")
        
        try:
            response = requests.post(
                f"{CAPTION_SERVER_URL}/api/duplicates/find-similar",
                json={
                    "selected_asset_ids": test_batch,
                    "threshold": threshold
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                groups = result.get('groups', [])
                print(f"  → {len(groups)} groupes trouvés")
                
                if groups:
                    for group in groups[:2]:  # Afficher max 2 groupes
                        imgs = [img.get('filename', 'N/A')[:20] for img in group['images']]
                        print(f"    • {', '.join(imgs)} (sim: {group['similarity_avg']:.1%})")
            else:
                print(f"  ❌ Erreur: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
    
    # 7. Test analyse d'album (si on a un album ID)
    print(f"\n{Colors.YELLOW}=== TEST ALBUM (optionnel) ==={Colors.END}")
    print("Pour tester l'analyse d'album, récupérez un album ID depuis Immich")
    
    print(f"\n{Colors.GREEN}🎉 Tests terminés!{Colors.END}")


def listen_sse_with_timeout(request_id, timeout=60):
    """Écouter le flux SSE avec timeout"""
    url = f"{CAPTION_SERVER_URL}/api/duplicates/find-similar-stream/{request_id}"
    
    print(f"\n{Colors.BLUE}📡 Écoute SSE...{Colors.END}")
    
    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            start_time = time.time()
            
            for line in response.iter_lines():
                if time.time() - start_time > timeout:
                    print(f"\n⏰ Timeout après {timeout}s")
                    break
                
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data:'):
                        try:
                            data = json.loads(line_str[5:])
                            event = data.get('event')
                            
                            if event == 'progress':
                                progress = data['data'].get('progress', 0)
                                details = data['data'].get('details', '')
                                step = data['data'].get('step', '')
                                
                                # Barre de progression
                                bar_length = 30
                                filled = int(bar_length * progress / 100)
                                bar = '█' * filled + '░' * (bar_length - filled)
                                
                                print(f"\r[{bar}] {progress}% - {step}: {details}", end='')
                                
                            elif event == 'result':
                                print()  # Nouvelle ligne
                                step = data['data'].get('step')
                                print(f"{Colors.GREEN}✓ {step} terminé{Colors.END}")
                                
                            elif event == 'complete':
                                print()  # Nouvelle ligne
                                result_data = data.get('data', {})
                                groups = result_data.get('groups', [])
                                
                                print(f"\n{Colors.GREEN}✅ Analyse terminée!{Colors.END}")
                                print(f"  • Groupes trouvés: {len(groups)}")
                                print(f"  • Doublons: {result_data.get('total_duplicates', 0)}")
                                
                                # Afficher quelques groupes
                                for i, group in enumerate(groups[:3]):
                                    print(f"\n  Groupe {i+1} (sim: {group['similarity_avg']:.1%}):")
                                    for img in group['images']:
                                        print(f"    - {img.get('filename', 'N/A')}")
                                
                                break
                                
                            elif event == 'error':
                                print()
                                error = data['data'].get('error', 'Erreur inconnue')
                                print(f"{Colors.RED}❌ Erreur: {error}{Colors.END}")
                                break
                                
                        except json.JSONDecodeError:
                            pass
                            
    except Exception as e:
        print(f"\n{Colors.RED}❌ Erreur SSE: {e}{Colors.END}")


if __name__ == "__main__":
    test_duplicates_detection()