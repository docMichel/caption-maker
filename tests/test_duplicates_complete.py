#!/usr/bin/env python3
"""
📍 test_duplicates_complete.py
Test complet du système de détection de doublons avec SSE
"""

import requests
import json
import base64
import time
import threading
from pathlib import Path
from PIL import Image
import numpy as np
import io

# Configuration
SERVER_URL = "http://localhost:5000"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'


def create_test_images():
    """Créer des images de test avec différents niveaux de similarité"""
    print(f"\n{Colors.YELLOW}📸 Création d'images de test...{Colors.END}")
    
    test_images = []
    
    # Image originale
    img1 = Image.new('RGB', (800, 600), color='red')
    # Ajouter un carré blanc
    for x in range(100, 200):
        for y in range(100, 200):
            img1.putpixel((x, y), (255, 255, 255))
    
    # Image très similaire (petit changement)
    img2 = img1.copy()
    # Ajouter un petit point bleu
    for x in range(300, 310):
        for y in range(300, 310):
            img2.putpixel((x, y), (0, 0, 255))
    
    # Image moyennement similaire (changement de couleur)
    img3 = Image.new('RGB', (800, 600), color='orange')
    # Même carré blanc
    for x in range(100, 200):
        for y in range(100, 200):
            img3.putpixel((x, y), (255, 255, 255))
    
    # Image différente
    img4 = Image.new('RGB', (800, 600), color='blue')
    # Cercle approximatif
    center_x, center_y = 400, 300
    radius = 100
    for x in range(800):
        for y in range(600):
            if (x - center_x)**2 + (y - center_y)**2 < radius**2:
                img4.putpixel((x, y), (255, 255, 0))
    
    # Image identique à img1 (vrai doublon)
    img5 = img1.copy()
    
    # Convertir en base64
    for i, img in enumerate([img1, img2, img3, img4, img5], 1):
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=95)
        img_data = buffer.getvalue()
        
        img_base64 = base64.b64encode(img_data).decode('utf-8')
        test_images.append({
            'asset_id': f'test-asset-{i:03d}',
            'filename': f'test_image_{i}.jpg',
            'base64': f"data:image/jpeg;base64,{img_base64}",
            'data': img_data,
            'description': [
                'Original rouge avec carré blanc',
                'Similaire à 1 (petit point bleu ajouté)',
                'Orange avec carré blanc (couleur différente)',
                'Complètement différent (bleu avec cercle)',
                'Doublon exact de 1'
            ][i-1]
        })
    
    print(f"{Colors.GREEN}✅ {len(test_images)} images de test créées{Colors.END}")
    return test_images


def test_endpoint(method, endpoint, description, data=None, timeout=30):
    """Tester un endpoint"""
    print(f"\n{Colors.YELLOW}Test:{Colors.END} {description}")
    print(f"Endpoint: {method} {endpoint}")
    
    try:
        url = f"{SERVER_URL}{endpoint}"
        
        if method == "GET":
            response = requests.get(url, timeout=timeout)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=timeout)
        
        if response.status_code == 200:
            print(f"{Colors.GREEN}✅ Success{Colors.END} (HTTP {response.status_code})")
            return response.json()
        else:
            print(f"{Colors.RED}❌ Failed{Colors.END} (HTTP {response.status_code})")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"{Colors.RED}❌ Error:{Colors.END} {e}")
        return None


def listen_sse_duplicates(request_id, duration=60):
    """Écouter le flux SSE pour la détection de doublons"""
    print(f"\n{Colors.BLUE}📡 Écoute SSE pour {request_id}...{Colors.END}")
    
    url = f"{SERVER_URL}/api/duplicates/find-similar-stream/{request_id}"
    
    try:
        response = requests.get(url, stream=True, headers={
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache'
        }, timeout=duration)
        
        start_time = time.time()
        final_result = None
        
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
                        
                        if event_type == 'connected':
                            print(f"{Colors.CYAN}🔗 {data.get('message', 'Connecté')}{Colors.END}")
                            
                        elif event_type == 'progress':
                            progress_data = data.get('data', {})
                            progress = progress_data.get('progress', 0)
                            details = progress_data.get('details', '')
                            step = progress_data.get('step', '')
                            
                            # Barre de progression visuelle
                            bar_length = 30
                            filled = int(bar_length * progress / 100)
                            bar = '█' * filled + '░' * (bar_length - filled)
                            
                            print(f"\r{Colors.CYAN}[{bar}] {progress}% - {step}: {details}{Colors.END}", end='')
                            
                        elif event_type == 'result':
                            print()  # Nouvelle ligne après progress
                            step = data['data'].get('step', 'unknown')
                            result_data = data['data'].get('result', {})
                            
                            if step == 'download':
                                print(f"{Colors.GREEN}📥 Téléchargement: {result_data.get('downloaded')}/{result_data.get('total')} images{Colors.END}")
                            else:
                                print(f"{Colors.GREEN}📊 Résultat [{step}]: {json.dumps(result_data, indent=2)}{Colors.END}")
                            
                        elif event_type == 'complete':
                            print()  # Nouvelle ligne
                            print(f"{Colors.GREEN}✅ Analyse terminée!{Colors.END}")
                            final_result = data.get('data', {})
                            
                            # Afficher le résumé
                            if 'groups' in final_result:
                                groups = final_result['groups']
                                print(f"\n{Colors.MAGENTA}📊 Résumé des doublons:{Colors.END}")
                                print(f"  • Groupes trouvés: {len(groups)}")
                                print(f"  • Images dupliquées: {final_result.get('total_duplicates', 0)}")
                                print(f"  • Seuil utilisé: {final_result.get('threshold', 0.85):.0%}")
                                
                                # Détails des groupes
                                for i, group in enumerate(groups):
                                    print(f"\n  {Colors.YELLOW}Groupe {i+1}:{Colors.END}")
                                    print(f"    • Similarité moyenne: {group['similarity_avg']:.1%}")
                                    print(f"    • Images ({len(group['images'])}):")
                                    for img in group['images']:
                                        print(f"      - {img.get('asset_id', 'N/A')} ({img.get('filename', 'N/A')})")
                            break
                            
                        elif event_type == 'error':
                            print()  # Nouvelle ligne
                            print(f"{Colors.RED}❌ Erreur: {data['data'].get('error', 'Erreur inconnue')}{Colors.END}")
                            break
                            
                        elif event_type == 'heartbeat':
                            # Ignorer les heartbeats
                            pass
                            
                    except json.JSONDecodeError:
                        if line_str.strip():  # Ignorer les lignes vides
                            print(f"\nRaw SSE: {line_str}")
                        
        return final_result
        
    except Exception as e:
        print(f"\n{Colors.RED}❌ SSE Error:{Colors.END} {e}")
        return None


def simulate_immich_endpoint(test_images):
    """Simuler un endpoint Immich pour les tests"""
    from flask import Flask, jsonify, send_file
    import threading
    
    app = Flask(__name__)
    
    # Mapping asset_id -> image data
    assets = {img['asset_id']: img for img in test_images}
    
    @app.route('/api/asset/<asset_id>/original', methods=['GET'])
    def get_asset_original(asset_id):
        if asset_id in assets:
            img_data = assets[asset_id]['data']
            return send_file(
                io.BytesIO(img_data),
                mimetype='image/jpeg',
                as_attachment=True,
                download_name=f"{asset_id}.jpg"
            )
        return jsonify({'error': 'Asset not found'}), 404
    
    @app.route('/api/assets/<asset_id>', methods=['GET'])
    def get_asset_info(asset_id):
        if asset_id in assets:
            return jsonify({
                'id': asset_id,
                'originalFileName': assets[asset_id]['filename'],
                'fileCreatedAt': '2024-01-01T12:00:00Z',
                'exifInfo': {'fileSizeInByte': len(assets[asset_id]['data'])}
            })
        return jsonify({'error': 'Asset not found'}), 404
    
    # Démarrer le serveur dans un thread
    thread = threading.Thread(
        target=lambda: app.run(port=3001, debug=False),
        daemon=True
    )
    thread.start()
    time.sleep(2)  # Attendre que le serveur démarre
    print(f"{Colors.CYAN}🎭 Serveur Immich simulé démarré sur le port 3001{Colors.END}")


def main():
    """Tests principaux"""
    print(f"{Colors.MAGENTA}🧪 Test Complet - Détection de Doublons avec SSE{Colors.END}")
    print("=" * 60)
    
    # 1. Créer les images de test
    test_images = create_test_images()
    
    # 2. Démarrer le serveur Immich simulé (optionnel)
    # simulate_immich_endpoint(test_images)
    
    # 3. Health check
    health = test_endpoint("GET", "/api/health", "Health Check")
    
    if not health:
        print(f"\n{Colors.RED}⚠️  Le serveur n'est pas accessible!{Colors.END}")
        return
    
    # 4. Vérifier le status du service de doublons
    print(f"\n{Colors.YELLOW}=== TEST STATUS SERVICE ==={Colors.END}")
    
    status = test_endpoint("GET", "/api/duplicates/status", "Status détection doublons")
    
    if status and status.get('clip_available'):
        print(f"{Colors.GREEN}✅ CLIP disponible{Colors.END}")
        model_info = status.get('model_info', {})
        print(f"  • Modèle: {model_info.get('model_name', 'N/A')}")
        print(f"  • Dimension embeddings: {model_info.get('embedding_dimension', 'N/A')}")
    else:
        print(f"{Colors.RED}❌ CLIP non disponible!{Colors.END}")
        print("Installer avec: pip install sentence-transformers")
        return
    
    # 5. Test synchrone (petit lot)
    print(f"\n{Colors.YELLOW}=== TEST SYNCHRONE (3 images) ==={Colors.END}")
    
    small_batch = [img['asset_id'] for img in test_images[:3]]
    
    sync_result = test_endpoint("POST", "/api/duplicates/find-similar", 
                               "Détection synchrone", {
        "selected_asset_ids": small_batch,
        "threshold": 0.80
    })
    
    if sync_result and sync_result.get('success'):
        print(f"Groupes trouvés: {sync_result.get('total_groups', 0)}")
    
    # 6. Test asynchrone avec SSE (toutes les images)
    print(f"\n{Colors.YELLOW}=== TEST ASYNCHRONE SSE (5 images) ==={Colors.END}")
    
    request_id = f"test-dup-{int(time.time())}"
    all_asset_ids = [img['asset_id'] for img in test_images]
    
    # Afficher les images testées
    print(f"\n{Colors.CYAN}Images à analyser:{Colors.END}")
    for img in test_images:
        print(f"  • {img['asset_id']}: {img['description']}")
    
    async_start = test_endpoint("POST", "/api/duplicates/find-similar-async",
                               "Démarrage détection async", {
        "request_id": request_id,
        "selected_asset_ids": all_asset_ids,
        "threshold": 0.75,  # Seuil plus bas pour voir plus de groupes
        "group_by_time": False  # Pas de fenêtre temporelle
    })
    
    if async_start and async_start.get('success'):
        print(f"Request ID: {request_id}")
        print(f"SSE URL: {async_start['sse_url']}")
        
        # Écouter le flux SSE
        final_result = listen_sse_duplicates(request_id, 60)
        
        # Analyse des résultats
        if final_result and final_result.get('groups'):
            print(f"\n{Colors.YELLOW}=== ANALYSE DES RÉSULTATS ==={Colors.END}")
            
            expected_groups = [
                "Images 1 et 5 (doublons exacts)",
                "Images 1, 2 et 5 (très similaires)",
                "Possiblement 3 avec 1,2,5 si seuil bas"
            ]
            
            print(f"\n{Colors.CYAN}Groupes attendus:{Colors.END}")
            for exp in expected_groups:
                print(f"  • {exp}")
    
    # 7. Test avec différents seuils
    print(f"\n{Colors.YELLOW}=== TEST SEUILS MULTIPLES ==={Colors.END}")
    
    thresholds = [0.95, 0.85, 0.70]
    
    for threshold in thresholds:
        print(f"\n{Colors.CYAN}Seuil: {threshold:.0%}{Colors.END}")
        
        result = test_endpoint("POST", "/api/duplicates/find-similar",
                              f"Test seuil {threshold:.0%}", {
            "selected_asset_ids": all_asset_ids,
            "threshold": threshold
        }, timeout=60)
        
        if result and result.get('success'):
            groups = result.get('groups', [])
            print(f"  → {len(groups)} groupes trouvés")
            for group in groups:
                img_ids = [img['asset_id'] for img in group['images']]
                print(f"    • {', '.join(img_ids)} (sim: {group['similarity_avg']:.1%})")
    
    # 8. Test analyse d'album (simulation)
    print(f"\n{Colors.YELLOW}=== TEST ANALYSE ALBUM ==={Colors.END}")
    
    album_result = test_endpoint("POST", "/api/duplicates/analyze-album/test-album-001",
                                "Analyse album complet", {
        "threshold": 0.80,
        "group_by_time": True,
        "time_window_hours": 24
    })
    
    if album_result and album_result.get('success'):
        print(f"Analyse démarrée: {album_result['request_id']}")
    
    # 9. Statistiques finales
    final_stats = test_endpoint("GET", "/api/duplicates/status", "Statistiques finales")
    
    if final_stats:
        stats = final_stats.get('stats', {})
        print(f"\n{Colors.MAGENTA}📊 Statistiques finales:{Colors.END}")
        print(f"  • Images traitées: {stats.get('total_images_processed', 0)}")
        print(f"  • Groupes trouvés: {stats.get('total_groups_found', 0)}")
        print(f"  • Taux de cache: {stats.get('cache_hit_rate', '0%')}")
    
    print(f"\n{Colors.GREEN}🎉 Tests terminés !{Colors.END}")


if __name__ == "__main__":
    main()