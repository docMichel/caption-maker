#!/usr/bin/env python3
"""
Script de test pour la détection de doublons
Usage: python test_duplicates.py [threshold]
"""

import requests
import json
import sys

# Récupérer le threshold depuis les arguments ou utiliser 0.95 par défaut
threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 0.95

print(f"🔍 Analyse avec seuil de similarité: {threshold:.0%}")
print("=" * 50)

url = "http://localhost:5001/api/duplicates/analyze-album/test"
response = requests.post(url, json={"threshold": threshold}, stream=True)

for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('data:'):
            data = json.loads(line_str[5:])
            
            if data['event'] == 'complete':
                print("\n🎉 RÉSULTATS:")
                groups = data['data']['groups']
                print(f"Nombre de groupes trouvés: {len(groups)}")
                
                if len(groups) == 0:
                    print("Aucun doublon détecté avec ce seuil.")
                
                for group in groups:
                    print(f"\n📁 Groupe {group['group_id']} (similarité moy: {group['similarity_avg']:.1%})")
                    for img in group['images']:
                        primary = " ⭐ (MEILLEURE)" if img['is_primary'] else ""
                        quality = f" - Qualité: {img.get('quality_score', 0):.0f}/100" if 'quality_score' in img else ""
                        blur = f", Flou: {img.get('blur_score', 0):.0f}" if 'blur_score' in img else ""
                        print(f"   - {img['filename']} ({img['similarity']:.1%}){primary}{quality}{blur}")
                        
            elif data['event'] == 'error':
                print(f"❌ Erreur: {data['data']['error']}")
                
            elif data['event'] == 'progress':
                print(f"⏳ {data['data']['details']} - {data['data']['progress']}%")

print("\n" + "=" * 50)
print(f"💡 Conseil: Essayez différents seuils (0.80 à 0.99)")
print(f"   python {sys.argv[0]} 0.90")