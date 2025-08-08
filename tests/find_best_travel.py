#!/usr/bin/env python3
"""Test des modèles pour Travel Llama fallback"""

import requests
import time

def test_travel_model(model_name):
    """Tester un modèle pour l'enrichissement touristique"""
    prompt = """Tu es un expert en voyage. 
    Enrichis avec des infos touristiques captivantes sur Tiébaghi, Nouvelle-Calédonie.
    Maximum 100 mots, style guide passionné."""
    
    try:
        start = time.time()
        response = requests.post("http://localhost:11434/api/generate", json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.8,
                "num_predict": 150
            }
        })
        
        duration = time.time() - start
        
        if response.status_code == 200:
            result = response.json()['response']
            print(f"\n{'='*60}")
            print(f"Modèle: {model_name}")
            print(f"Temps: {duration:.1f}s")
            print(f"Réponse:\n{result}")
            print(f"Qualité: {'⭐' * (5 if 'mine' in result.lower() else 3)}")
            return True
        else:
            print(f"❌ {model_name}: Erreur {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ {model_name}: {e}")
        return False

# Tester les modèles disponibles
print("🧪 Test des modèles pour Travel Llama fallback")

models_to_test = [
    "llama3.1:8b",
    "mistral:7b-instruct", 
    "qwen2:7b",
    "mixtral:8x7b",
    "phi3:mini",
    "gemma2:9b"
]

available = []
for model in models_to_test:
    if test_travel_model(model):
        available.append(model)

print(f"\n✅ Modèles disponibles pour fallback: {available}")
print(f"💡 Recommandation: Utilisez '{available[0]}' comme fallback")