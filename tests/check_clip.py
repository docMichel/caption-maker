# test_clip.py - Tester si CLIP fonctionne
import sys

try:
    from sentence_transformers import SentenceTransformer
    print("✅ sentence-transformers installé")
    
    # Tester le chargement du modèle
    print("Chargement du modèle CLIP...")
    model = SentenceTransformer('clip-ViT-B-32')
    print("✅ Modèle CLIP chargé avec succès")
    
    # Info sur le modèle
    print(f"Dimension des embeddings: {model.get_sentence_embedding_dimension()}")
    
except ImportError:
    print("❌ sentence-transformers non installé")
    print("Installer avec: pip install sentence-transformers")
    sys.exit(1)
except Exception as e:
    print(f"❌ Erreur: {e}")
    sys.exit(1)