#!/usr/bin/env python3
"""
Test de disponibilité et fonctionnement de Travel Llama
"""

import requests
import json
import time

def test_ollama_connection(base_url="http://localhost:11434"):
    """Tester la connexion à Ollama"""
    print(f"🔌 Test connexion Ollama sur {base_url}")
    try:
        response = requests.get(f"{base_url}/api/version", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama est accessible")
            return True
        else:
            print(f"❌ Ollama retourne code {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Erreur connexion Ollama: {e}")
        return False

def list_available_models(base_url="http://localhost:11434"):
    """Lister tous les modèles disponibles"""
    print("\n📋 Liste des modèles disponibles:")
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            if models:
                for model in models:
                    name = model.get('name', 'unknown')
                    size = model.get('size', 0) / (1024**3)  # Convert to GB
                    modified = model.get('modified_at', '')[:10]
                    print(f"   - {name} ({size:.1f}GB) - modifié: {modified}")
                return [m['name'] for m in models]
            else:
                print("   ⚠️ Aucun modèle trouvé")
                return []
        else:
            print(f"   ❌ Erreur: code {response.status_code}")
            return []
    except Exception as e:
        print(f"   ❌ Erreur listing: {e}")
        return []

def test_model_generation(model_name, base_url="http://localhost:11434"):
    """Tester la génération avec un modèle spécifique"""
    print(f"\n🧪 Test du modèle: {model_name}")
    
    prompt = """Tu es Travel Llama, expert en voyage. 
    Enrichis cette description avec des infos touristiques.
    Lieu: Nouvelle-Calédonie
    Réponds en 2-3 phrases maximum."""
    
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 100
        }
    }
    
    try:
        print("   ⏳ Génération en cours...")
        start_time = time.time()
        
        response = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=60
        )
        
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('response', '').strip()
            
            if text:
                print(f"   ✅ Succès en {elapsed:.1f}s")
                print(f"   📝 Réponse: {text[:200]}...")
                return True
            else:
                print(f"   ❌ Réponse vide")
                return False
        else:
            print(f"   ❌ Erreur HTTP {response.status_code}")
            print(f"   Détails: {response.text[:200]}")
            return False
            
    except requests.Timeout:
        print(f"   ⏱️ Timeout après 60s")
        return False
    except Exception as e:
        print(f"   ❌ Erreur: {e}")
        return False

def pull_model(model_name, base_url="http://localhost:11434"):
    """Télécharger un modèle s'il n'est pas disponible"""
    print(f"\n📥 Téléchargement du modèle: {model_name}")
    print("   ⚠️ Cela peut prendre plusieurs minutes...")
    
    payload = {
        "name": model_name,
        "stream": True
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/pull",
            json=payload,
            stream=True,
            timeout=None  # Pas de timeout pour le téléchargement
        )
        
        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    status = data.get('status', '')
                    
                    if 'pulling' in status:
                        completed = data.get('completed', 0) / (1024**3)
                        total = data.get('total', 0) / (1024**3)
                        if total > 0:
                            percent = (completed / total) * 100
                            print(f"   📊 Progression: {percent:.1f}% ({completed:.1f}/{total:.1f} GB)", end='\r')
                    elif 'success' in status.lower():
                        print(f"\n   ✅ {status}")
                    else:
                        print(f"   ℹ️ {status}")
                        
                except json.JSONDecodeError:
                    continue
                    
        print("\n   ✅ Téléchargement terminé")
        return True
        
    except Exception as e:
        print(f"\n   ❌ Erreur téléchargement: {e}")
        return False

def main():
    """Test principal"""
    print("🌍 TEST TRAVEL LLAMA")
    print("=" * 50)
    
    base_url = "http://localhost:11434"
    
    # 1. Tester la connexion
    if not test_ollama_connection(base_url):
        print("\n❌ Ollama n'est pas accessible. Vérifiez qu'il est lancé.")
        return
    
    # 2. Lister les modèles
    available_models = list_available_models(base_url)
    
    # 3. Modèles à tester
    travel_models = [
        "llama3.1:70b",      # Modèle principal
        "llama3.1:8b",       # Version plus légère
        "llama3.1:latest",   # Version par défaut
        "mistral:7b-instruct" # Fallback
    ]
    
    print("\n🔍 Recherche des modèles Travel Llama...")
    found_models = []
    
    for model in travel_models:
        if model in available_models:
            print(f"   ✅ {model} est installé")
            found_models.append(model)
        else:
            print(f"   ❌ {model} n'est pas installé")
    
    # 4. Tester les modèles trouvés
    if found_models:
        print("\n🧪 Test des modèles trouvés:")
        working_models = []
        
        for model in found_models:
            if test_model_generation(model, base_url):
                working_models.append(model)
        
        if working_models:
            print(f"\n✅ Modèles fonctionnels: {', '.join(working_models)}")
            print(f"💡 Recommandation: utilisez '{working_models[0]}' comme modèle principal")
        else:
            print("\n❌ Aucun modèle ne fonctionne correctement")
    else:
        print("\n⚠️ Aucun modèle Travel Llama trouvé")
        print("\n💡 Pour installer llama3.1, exécutez:")
        print("   ollama pull llama3.1:8b    # Version légère (4.9GB)")
        print("   ollama pull llama3.2:3b   # Version complète (40GB)")
        
        # Proposer le téléchargement
        response = input("\nVoulez-vous télécharger llama3.1:8b maintenant? (o/n): ")
        if response.lower() == 'o':
            if pull_model("llama3.1:8b", base_url):
                print("\n🎉 Installation réussie! Relancez ce test.")
            else:
                print("\n❌ Échec de l'installation")

if __name__ == "__main__":
    main()