# API Immich - Référence pour Caption Maker

Documentation des endpoints Immich testés et fonctionnels pour le projet Caption Maker.

## Configuration requise

- **Proxy URL**: `http://localhost:3001`
- **Headers requis**: 
  - `x-api-key: VOTRE_CLE_API` (en minuscules !)
  - `X-API-Key: VOTRE_CLE_API` (certaines versions)

## 1. Informations Asset

### Récupérer les métadonnées d'un asset
```
GET /api/assets/{asset_id}
```
**Réponse**: JSON avec toutes les infos de l'asset (type, filename, size, etc.)

## 2. Images et Thumbnails

### Thumbnail par défaut
```
GET /api/assets/{asset_id}/thumbnail
```
**Utilisation**: Miniature standard

### Thumbnail avec taille spécifique
```
GET /api/assets/{asset_id}/thumbnail?size={size}
```
**Paramètres size**:
- `thumbnail` - Petite miniature (webp)
- `preview` - Taille moyenne pour prévisualisation
- `fullsize` - Grande taille (mais pas l'original)

**Exemples**:
```
GET /api/assets/{asset_id}/thumbnail?size=thumbnail
GET /api/assets/{asset_id}/thumbnail?size=preview
GET /api/assets/{asset_id}/thumbnail?size=fullsize
```

### Image originale
```
GET /api/assets/{asset_id}/original
```
**Utilisation**: Image complète non modifiée, idéale pour la détection de doublons

## 3. Recherche et listage d'assets

### Rechercher/Lister tous les assets (MODERNE)
```
POST /api/search/metadata
```
**Body JSON**:
```json
{
  "page": 1,
  "size": 20
}
```
**Note**: Sans filtres, retourne tous les assets. C'est l'endpoint recommandé pour lister des assets.

**Réponse**: 
```json
{
  "assets": {
    "items": [
      {
        "id": "asset-id",
        "originalFileName": "photo.jpg",
        "fileCreatedAt": "2024-01-01T12:00:00Z",
        // ... autres métadonnées
      }
    ]
  }
}
```

### Recherche avec filtres
```
POST /api/search/metadata
```
**Body avec filtres**:
```json
{
  "page": 1,
  "size": 20,
  "isOffline": false,
  "isArchived": false,
  "withArchived": true,  // Pour inclure les archivés
  "libraryId": "library-id"  // Optionnel
}
```

## 4. Albums

### Lister tous les albums
```
GET /api/albums
```
**Réponse**: Liste de tous les albums de l'utilisateur

### Récupérer un album avec ses assets
```
GET /api/albums/{album_id}
```
**Réponse**: Détails de l'album incluant la liste `assets`

### Créer un album
```
POST /api/albums
```
**Body**:
```json
{
  "albumName": "Nom de l'album",
  "description": "Description optionnelle"
}
```

### Ajouter des assets à un album
```
PUT /api/albums/{album_id}/assets
```
**Body**:
```json
{
  "ids": ["asset-id-1", "asset-id-2"]
}
```

## 5. Reconnaissance faciale

### Récupérer les visages d'un asset
Plusieurs endpoints possibles selon la version Immich :
```
GET /api/face?assetId={asset_id}
GET /api/asset/{asset_id}/faces
GET /api/faces/asset/{asset_id}
```

### Liste des personnes
```
GET /api/person
```
**Réponse**: Liste des personnes identifiées avec leurs IDs

## 6. Informations serveur

### Version du serveur (pour test de connexion)
```
GET /api/server-info/version
GET /api/server/version
GET /api/server-info
```

## Exemples d'utilisation dans le code

### Python - Récupérer tous les assets
```python
# Méthode moderne recommandée
url = f"{proxy_url}/api/search/metadata"
data = {"page": 1, "size": 100}
response = requests.post(url, 
    headers={'x-api-key': api_key},
    json=data
)
assets = response.json()['assets']['items']
```

### Python - Récupérer les assets d'un album
```python
# 1. Lister les albums
albums_response = requests.get(
    f"{proxy_url}/api/albums",
    headers={'x-api-key': api_key}
)
albums = albums_response.json()

# 2. Récupérer un album avec ses assets
album_id = albums[0]['id']
album_response = requests.get(
    f"{proxy_url}/api/albums/{album_id}",
    headers={'x-api-key': api_key}
)
assets = album_response.json()['assets']
```

### Python - Télécharger une image pour détection de doublons
```python
# Pour preview (recommandé pour rapidité)
url = f"{proxy_url}/api/assets/{asset_id}/thumbnail?size=preview"

# Pour original (meilleure précision)
url = f"{proxy_url}/api/assets/{asset_id}/original"

response = requests.get(url, headers={'x-api-key': api_key})
image_data = response.content
```

### JavaScript - Récupérer un thumbnail
```javascript
const response = await fetch(
  `/api/assets/${assetId}/thumbnail?size=preview`,
  { headers: { 'x-api-key': apiKey } }
);
```

## Endpoints qui NE fonctionnent PAS

❌ `/api/asset` (endpoint supprimé)
❌ `/api/assets` (GET pour lister - utiliser searchMetadata)
❌ `/api/asset/thumbnail/{id}` (singulier)
❌ `/api/assets/thumbnail/{id}` (ordre inversé)
❌ `/api/assets/{id}/preview` (endpoint direct)
❌ `/api/assets/{id}/fullsize` (endpoint direct)
❌ `/api/asset/file/{id}`
❌ `/api/asset/download/{id}`

## Notes importantes

1. **Toujours utiliser le pluriel** : `/api/assets/` et non `/api/asset/`
2. **L'ordre compte** : `/api/assets/{id}/thumbnail` et non `/api/assets/thumbnail/{id}`
3. **Paramètres de taille** : Utiliser `?size=` pour spécifier la taille
4. **Cache** : Les images sont souvent cachées côté client, prévoir un système de cache local
5. **Headers API Key** : Utiliser `x-api-key` en minuscules pour la plupart des endpoints
6. **Listage d'assets** : Utiliser `/api/search/metadata` sans filtres pour obtenir tous les assets

## Recommandations pour Caption Maker

- **Pour l'affichage web** : Utiliser `thumbnail?size=preview`
- **Pour la détection de doublons** : Utiliser `/original` ou `thumbnail?size=fullsize`
- **Pour les miniatures de galerie** : Utiliser `thumbnail?size=thumbnail`
- **Pour lister des assets** : Utiliser `searchMetadata` ou passer par les albums

## Gestion des erreurs

- **401** : Clé API invalide ou manquante
- **404** : Asset non trouvé ou endpoint incorrect
- **500** : Erreur serveur Immich

## Exemple complet de fonction
```python
def get_immich_image(asset_id: str, size: str = 'preview') -> bytes:
    """Récupérer une image depuis Immich"""
    
    if size == 'original':
        url = f"{PROXY_URL}/api/assets/{asset_id}/original"
    else:
        # thumbnail, preview ou fullsize
        url = f"{PROXY_URL}/api/assets/{asset_id}/thumbnail?size={size}"
    
    response = requests.get(url, headers={'x-api-key': API_KEY})
    response.raise_for_status()
    
    return response.content
```

## Fonction pour récupérer des assets
```python
def get_all_assets(limit=100):
    """Récupérer tous les assets via searchMetadata"""
    
    url = f"{PROXY_URL}/api/search/metadata"
    headers = {'x-api-key': API_KEY}
    
    # Sans filtres = tous les assets
    data = {
        "page": 1,
        "size": limit
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        result = response.json()
        # Format peut varier selon version
        if 'assets' in result and 'items' in result['assets']:
            return result['assets']['items']
        elif isinstance(result, list):
            return result
    
    return []
```