#!/bin/bash
# Script d'installation des dépendances pour la détection de doublons

echo "🎯 Installation des dépendances pour détection de doublons..."

# Activer l'environnement virtuel
cd "$(dirname "$0")/../.."
source venv/bin/activate

# Installer sentence-transformers et sklearn
echo "📦 Installation de sentence-transformers..."
pip install sentence-transformers scikit-learn

# Test de l'installation
echo "🧪 Test de l'installation..."
python tests/check_clip.py

if [ $? -eq 0 ]; then
    echo "✅ Installation réussie!"
    echo "Le service de détection de doublons est maintenant disponible."
else
    echo "❌ Échec de l'installation"
    echo "Vérifiez les erreurs ci-dessus."
    exit 1
fi

echo ""
echo "📝 Pour utiliser la détection de doublons:"
echo "1. Redémarrez le serveur Caption Maker"
echo "2. Vérifiez le status: GET /api/duplicates/status"
echo "3. Utilisez l'API: POST /api/duplicates/find-similar"