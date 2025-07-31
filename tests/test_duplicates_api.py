#!/usr/bin/env python3
"""
📍 test_duplicates_api.py
Test de l'API de détection de doublons
Compatible avec le serveur Caption Maker
"""

import requests
import json
import base64
import time
import threading
from pathlib import Path

# Configuration
SERVER_URL = "http://localhost:5000"
TEST_IMAGES = ["test1.jpg", "test2.jpg", "test3.jpg"]  # Images similaires pour tester

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def test_endpoint(method, endpoint, description, data=None):
    """Tester un endpoint"""
    print(f"\n{Colors.YELLOW}Test:{Colors.END} {description}")
    print(f"Endpoint: {method} {endpoint}")
    
    try:
        url = f"{SERVER_URL}{endpoint}"
        
        if method == "GET":
            response = requests.get(url)
        elif method == "POST":
            response = requests.post(url, json=data)
        
        if response.status_code == 200:
            print(f"{Colors.GREEN}✅ Success{Colors.END} (HTTP {response.status_code})")
            print(json.dumps(response.json(), indent=2))
            return response.json()
        else:
            print(f"{Colors.RED}❌ Failed{Colors.END} (HTTP {response.status_code})")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"{Colors.RED}❌ Error:{Colors.END} {e}")
        return None

def encode_image(image_path):
    """Encoder une image en base64"""
    with open(image_path, 'rb') as f:
        image_data = f.read()
    base64_data = base64.b64encode(image_data).decode('utf-8')
    return f"data:image/jpeg;base64,{base64_data}"

def listen_sse(endpoint, duration=60):
    """Écouter le flux SSE pour l'analyse d'album"""
    print(f"\n{Colors.BLUE}📡 Écoute SSE {endpoint}...{Colors.END}")
    
    url = f"{SERVER_URL}{endpoint}"
    
    try:
        response = requests.get(url, stream=True, headers={
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache'
        }, json={'threshold': 0.85})
        
        start_time = time.time()
        
        for line in response.iter_lines():
            if time.time() - start_time > duration:
                print("⏰ Timeout SSE")
                break
                
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data:'):
                    try:
                        data = json.loads(line_str[5:])
                        event_type = data.get('event', 'unknown')
                        
                        if event_type == 'progress':
                            progress = data['data']['progress']
                            details = data['data']['details']
                            print(f"📊 Progress: {progress}% - {details}")
                            
                        elif event_type == 'complete':
                            print(f"{Colors.GREEN}✅ Analyse terminée!{Colors.END}")
                            groups = data['data']['groups']
                            print(f"Groupes trouvés: {len(groups)}")
                            for group in groups[:3]:  # Afficher les 3 premiers
                                print(f"\nGroupe {group['group_id']}:")
                                print(f"  Similarité moyenne: {group['similarity_avg']:.2%}")
                                print(f"  Images ({len(group['images'])}):")
                                for img in group['images']:
                                    print(f"    - {img['filename']} {'[PRIMARY]' if img['is_primary'] else ''}")
                            break
                            
                        elif event_type == 'error':
                            print(f"{Colors.RED}❌ Error: {data['data']['error']}{Colors.END}")
                            break
                            
                    except json.JSONDecodeError:
                        print(f"Raw SSE: {line_str}")
                        
    except Exception as e:
        print(f"{Colors.RED}❌ SSE Error:{Colors.END} {e}")

def main():
    """Tests principaux"""
    print("🧪 Test API Détection de Doublons - Caption Maker")
    print("=" * 50)
    
    # 1. Health check
    health = test_endpoint("GET", "/api/health", "Health Check")
    
    if not health or health.get('status') != 'healthy':
        print(f"\n{Colors.RED}⚠️  Le serveur n'est pas healthy!{Colors.END}")
        return
    
    # 2. Vérifier si CLIP est disponible
    print(f"\n{Colors.YELLOW}=== TEST DISPONIBILITÉ CLIP ==={Colors.END}")
    
    clip_status = test_endpoint("GET", "/api/duplicates/status", "Status détection doublons")
    
    if not clip_status or not clip_status.get('clip_available'):
        print(f"\n{Colors.RED}⚠️  CLIP n'est pas disponible!{Colors.END}")
        print("Installer avec: pip install sentence-transformers")
        return
    
    # 3. Test de recherche de similaires
    print(f"\n{Colors.YELLOW}=== TEST RECHERCHE IMAGES SIMILAIRES ==={Colors.END}")
    
    # Simuler un asset_id Immich
    test_asset_id = "test-asset-001"
    
    similar_result = test_endpoint("POST", "/api/duplicates/find-similar", "Recherche similaires", {
        "asset_id": test_asset_id,
        "threshold": 0.85,
        "time_window": 24
    })
    
    if similar_result and similar_result.get('success'):
        print(f"\n{Colors.GREEN}Images similaires trouvées:{Colors.END}")
        print(f"Source: {similar_result['source_asset']['filename']}")
        print(f"Similaires: {similar_result['total_found']}")
        
        for img in similar_result['similar_images'][:5]:
            print(f"  - {img['filename']} (similarité: {img['similarity']:.2%})")
    
    # 4. Test avec upload d'image locale
    if Path(TEST_IMAGES[0]).exists():
        print(f"\n{Colors.YELLOW}=== TEST AVEC IMAGE LOCALE ==={Colors.END}")
        
        image_base64 = encode_image(TEST_IMAGES[0])
        
        local_result = test_endpoint("POST", "/api/duplicates/find-similar-from-upload", 
                                   "Recherche depuis upload", {
            "image_base64": image_base64,
            "album_id": "test-album-001",
            "threshold": 0.80
        })
        
        if local_result and local_result.get('success'):
            print(f"Similaires trouvés: {local_result['total_found']}")
    
    # 5. Test analyse d'album complet avec SSE
    print(f"\n{Colors.YELLOW}=== TEST ANALYSE ALBUM COMPLET ==={Colors.END}")
    
    album_id = "test-album-001"
    
    # Démarrer l'analyse dans un thread pour écouter le SSE
    sse_thread = threading.Thread(
        target=listen_sse,
        args=(f"/api/duplicates/analyze-album/{album_id}", 120)
    )
    sse_thread.start()
    sse_thread.join()
    
    # 6. Test de groupement manuel
    print(f"\n{Colors.YELLOW}=== TEST GROUPEMENT MANUEL ==={Colors.END}")
    
    group_result = test_endpoint("POST", "/api/duplicates/create-group", "Créer groupe manuel", {
        "album_id": album_id,
        "asset_ids": ["asset-001", "asset-002", "asset-003"],
        "group_name": "Sunset variations"
    })
    
    # 7. Test suppression de doublons
    print(f"\n{Colors.YELLOW}=== TEST ACTIONS SUR DOUBLONS ==={Colors.END}")
    
    action_result = test_endpoint("POST", "/api/duplicates/process-group", "Traiter un groupe", {
        "group_id": "group_0",
        "action": "keep_best",  # ou "merge_metadata" ou "delete_duplicates"
        "primary_asset_id": "asset-001"
    })
    
    # 8. Statistiques
    stats = test_endpoint("GET", f"/api/duplicates/stats/{album_id}", "Statistiques doublons")
    
    if stats:
        print(f"\n{Colors.BLUE}📊 Statistiques album:{Colors.END}")
        print(f"  Total images: {stats.get('total_images', 0)}")
        print(f"  Groupes de doublons: {stats.get('duplicate_groups', 0)}")
        print(f"  Images dupliquées: {stats.get('duplicate_images', 0)}")
        print(f"  Espace récupérable: {stats.get('space_savings', '0 MB')}")
    
    print(f"\n{Colors.GREEN}🎉 Tests terminés !{Colors.END}")

if __name__ == "__main__":
    main()