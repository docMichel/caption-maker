# Ajouter dans votre serveur Flask existant

from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timedelta
import hashlib

# Initialiser CLIP au démarrage
clip_model = None

def init_clip():
    global clip_model
    try:
        clip_model = SentenceTransformer('clip-ViT-B-32')
        logger.info("✅ Modèle CLIP initialisé")
        return True
    except Exception as e:
        logger.error(f"❌ Erreur CLIP: {e}")
        return False

# Cache des embeddings
embeddings_cache = {}

def get_image_embedding(image_path):
    """Obtenir l'embedding d'une image avec cache"""
    # Clé de cache basée sur le chemin et la date de modification
    cache_key = hashlib.md5(f"{image_path}_{os.path.getmtime(image_path)}".encode()).hexdigest()
    
    if cache_key in embeddings_cache:
        return embeddings_cache[cache_key]
    
    # Charger et encoder l'image
    image = Image.open(image_path).convert('RGB')
    embedding = clip_model.encode(image)
    
    embeddings_cache[cache_key] = embedding
    return embedding

@app.route('/api/duplicates/find-similar', methods=['POST'])
def find_similar_images():
    """Trouver les images similaires à partir d'une image source"""
    try:
        data = request.json
        source_asset_id = data.get('asset_id')
        threshold = data.get('threshold', 0.85)
        time_window_hours = data.get('time_window', 24)
        
        if not source_asset_id:
            return jsonify({'error': 'asset_id requis'}), 400
        
        # 1. Récupérer l'image source depuis Immich
        source_path = get_immich_asset_path(source_asset_id)
        source_metadata = get_immich_asset_metadata(source_asset_id)
        source_date = datetime.fromisoformat(source_metadata['fileCreatedAt'])
        
        # 2. Obtenir l'embedding de l'image source
        source_embedding = get_image_embedding(source_path)
        
        # 3. Récupérer tous les assets du même album dans la fenêtre temporelle
        album_id = source_metadata.get('albumId')
        candidates = get_album_assets_in_timewindow(
            album_id, 
            source_date - timedelta(hours=time_window_hours),
            source_date + timedelta(hours=time_window_hours)
        )
        
        # 4. Calculer les similarités
        similar_images = []
        
        for candidate in candidates:
            if candidate['id'] == source_asset_id:
                continue
                
            candidate_path = get_immich_asset_path(candidate['id'])
            candidate_embedding = get_image_embedding(candidate_path)
            
            # Calculer la similarité cosinus
            similarity = cosine_similarity(
                source_embedding.reshape(1, -1),
                candidate_embedding.reshape(1, -1)
            )[0][0]
            
            if similarity >= threshold:
                similar_images.append({
                    'asset_id': candidate['id'],
                    'similarity': float(similarity),
                    'filename': candidate['originalFileName'],
                    'date': candidate['fileCreatedAt'],
                    'thumbnail_url': f"/api/assets/{candidate['id']}/thumbnail"
                })
        
        # 5. Trier par similarité décroissante
        similar_images.sort(key=lambda x: x['similarity'], reverse=True)
        
        return jsonify({
            'success': True,
            'source_asset': {
                'id': source_asset_id,
                'filename': source_metadata['originalFileName']
            },
            'similar_images': similar_images,
            'total_found': len(similar_images)
        })
        
    except Exception as e:
        logger.error(f"Erreur find_similar: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/duplicates/analyze-album/<album_id>', methods=['POST'])
def analyze_album_duplicates(album_id):
    """Analyser tout un album pour trouver les groupes de doublons"""
    try:
        threshold = request.json.get('threshold', 0.85)
        
        # Utiliser SSE pour le progress
        def generate():
            yield f"data: {json.dumps({'event': 'start', 'data': {'album_id': album_id}})}\n\n"
            
            # 1. Récupérer tous les assets de l'album
            assets = get_album_assets(album_id)
            total = len(assets)
            
            yield f"data: {json.dumps({'event': 'progress', 'data': {'progress': 0, 'details': f'Analyse de {total} images'}})}\n\n"
            
            # 2. Calculer tous les embeddings
            embeddings = []
            for i, asset in enumerate(assets):
                asset_path = get_immich_asset_path(asset['id'])
                embedding = get_image_embedding(asset_path)
                embeddings.append(embedding)
                
                if i % 10 == 0:
                    progress = int((i / total) * 50)
                    yield f"data: {json.dumps({'event': 'progress', 'data': {'progress': progress, 'details': f'Encodage: {i}/{total}'}})}\n\n"
            
            # 3. Calculer la matrice de similarité
            yield f"data: {json.dumps({'event': 'progress', 'data': {'progress': 50, 'details': 'Calcul des similarités'}})}\n\n"
            
            embeddings_matrix = np.array(embeddings)
            similarity_matrix = cosine_similarity(embeddings_matrix)
            
            # 4. Regrouper les images similaires
            groups = []
            processed = set()
            
            for i in range(len(assets)):
                if i in processed:
                    continue
                    
                group = [i]
                processed.add(i)
                
                # Trouver toutes les images similaires
                for j in range(i + 1, len(assets)):
                    if j not in processed and similarity_matrix[i][j] >= threshold:
                        # Vérifier aussi la proximité temporelle
                        time_diff = abs(
                            datetime.fromisoformat(assets[i]['fileCreatedAt']) - 
                            datetime.fromisoformat(assets[j]['fileCreatedAt'])
                        ).total_seconds() / 3600
                        
                        if time_diff <= 24:  # 24 heures
                            group.append(j)
                            processed.add(j)
                
                if len(group) > 1:
                    groups.append({
                        'group_id': f"group_{len(groups)}",
                        'images': [
                            {
                                'asset_id': assets[idx]['id'],
                                'filename': assets[idx]['originalFileName'],
                                'date': assets[idx]['fileCreatedAt'],
                                'is_primary': idx == group[0]
                            }
                            for idx in group
                        ],
                        'similarity_avg': float(np.mean([
                            similarity_matrix[group[0]][idx] 
                            for idx in group[1:]
                        ]))
                    })
                
                progress = 50 + int((i / total) * 50)
                yield f"data: {json.dumps({'event': 'progress', 'data': {'progress': progress, 'details': f'Regroupement: {i}/{total}'}})}\n\n"
            
            # 5. Retourner les résultats
            yield f"data: {json.dumps({'event': 'complete', 'data': {'groups': groups, 'total_groups': len(groups)}})}\n\n"
            
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        logger.error(f"Erreur analyze_album: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Ajouter dans votre fonction main ou d'initialisation
if __name__ == '__main__':
    init_clip()  # Initialiser CLIP au démarrage
    app.run(debug=True, port=5000)