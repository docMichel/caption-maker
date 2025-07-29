#!/usr/bin/env python3
"""
📍 test_api.py
Test Python du serveur Caption Maker
"""

import requests
import json
import base64
import time
import threading
from pathlib import Path

# Configuration
SERVER_URL = "http://localhost:5000"
TEST_IMAGE = "test.jpg"

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

def listen_sse(request_id, duration=30):
    """Écouter le flux SSE"""
    print(f"\n{Colors.BLUE}📡 Écoute SSE pour {request_id}...{Colors.END}")
    
    url = f"{SERVER_URL}/api/ai/generate-caption-stream/{request_id}"
    
    try:
        response = requests.get(url, stream=True, headers={
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache'
        })
        
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
                            
                        elif event_type == 'result':
                            step = data['data']['step']
                            print(f"📝 Result [{step}]: {json.dumps(data['data']['result'], indent=2)}")
                            
                        elif event_type == 'complete':
                            print(f"{Colors.GREEN}✅ Complete!{Colors.END}")
                            print(json.dumps(data['data'], indent=2))
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
    print("🧪 Test API Caption Maker")
    print("=" * 50)
    
    # 1. Health check
    health = test_endpoint("GET", "/api/health", "Health Check")
    
    if not health or health.get('status') != 'healthy':
        print(f"\n{Colors.RED}⚠️  Le serveur n'est pas healthy!{Colors.END}")
        return
    
    # 2. Configuration
    config = test_endpoint("GET", "/api/ai/config", "Configuration IA")
    
    # 3. Stats
    stats = test_endpoint("GET", "/api/ai/stats", "Statistiques")
    
    # 4. Préparer l'image
    if not Path(TEST_IMAGE).exists():
        print(f"\n{Colors.RED}⚠️  Créez une image {TEST_IMAGE} pour tester{Colors.END}")
        return
    
    print(f"\n{Colors.YELLOW}Encodage image...{Colors.END}")
    image_base64 = encode_image(TEST_IMAGE)
    print(f"{Colors.GREEN}✅ Image encodée{Colors.END} ({len(image_base64)} caractères)")
    
    # 5. Test synchrone
    '''    
    print(f"\n{Colors.YELLOW}=== TEST GÉNÉRATION SYNCHRONE ==={Colors.END}")
    
    sync_result = test_endpoint("POST", "/api/ai/generate-caption", "Génération synchrone", {
        "asset_id": "test-sync-001",
        "image_base64": image_base64,
        "latitude": 48.8566,
        "longitude": 2.3522,
        "language": "français",
        "style": "creative"
    })
    
    if sync_result and sync_result.get('success'):
        print(f"\n{Colors.GREEN}Légende générée:{Colors.END}")
        print(f'"{sync_result["caption"]}"')
        print(f"Confiance: {sync_result['confidence_score']:.2f}")
        print(f"Temps: {sync_result['generation_time']:.1f}s")
    '''
    # 6. Test asynchrone avec SSE
    print(f"\n{Colors.YELLOW}=== TEST GÉNÉRATION ASYNCHRONE ==={Colors.END}")
    
    request_id = f"test-async-{int(time.time())}"
    
    async_start = test_endpoint("POST", "/api/ai/generate-caption-async", "Démarrage async", {
        "request_id": request_id,
        "asset_id": "test-async-001",
        "image_base64": image_base64,
        "latitude": -22.2697,
        "longitude": 166.4381,
        "language": "français",
        "style": "descriptive"
    })
    
    if async_start and async_start.get('success'):
        # Écouter le flux SSE dans un thread
        sse_thread = threading.Thread(
            target=listen_sse,
            args=(request_id, 60)  # 60 secondes max
        )
        sse_thread.start()
        sse_thread.join()
    
    # 7. Test régénération
    print(f"\n{Colors.YELLOW}=== TEST RÉGÉNÉRATION ==={Colors.END}")
    
    regen_result = test_endpoint("POST", "/api/ai/regenerate-final", "Régénération finale", {
        "image_description": "Une magnifique plage de sable blanc avec des palmiers",
        "geo_context": "Nouméa, Nouvelle-Calédonie",
        "cultural_enrichment": "Lagon inscrit au patrimoine mondial de l'UNESCO",
        "language": "français",
        "style": "minimal"
    })
    
    if regen_result and regen_result.get('success'):
        print(f"\n{Colors.GREEN}Légende régénérée:{Colors.END}")
        print(f'"{regen_result["caption"]}"')
    
    # 8. Info cache
    cache_info = test_endpoint("GET", "/api/ai/cache/info", "Informations cache")
    
    # 9. Vider le cache
    clear_result = test_endpoint("POST", "/api/ai/clear-cache", "Vider le cache", {})
    
    print(f"\n{Colors.GREEN}🎉 Tests terminés !{Colors.END}")

if __name__ == "__main__":
    main()