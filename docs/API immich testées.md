# API Immich - Référence pour Caption Maker

Documentation des endpoints Immich testés et fonctionnels pour le projet Caption Maker.

## Configuration requise

- **Proxy URL**: `http://localhost:3001`
- **Headers requis**: 
  - `x-api-key: VOTRE_CLE_API`
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

## 3. Reconnaissance faciale

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

## 4. Informations serveur

### Version du serveur (pour test de connexion)
```
GET /api/server-info/version
GET /api/server/version
GET /api/server-info
```

## Exemples d'utilisation dans le code

### Python - Télécharger une image pour détection de doublons
```python
# Pour preview (recommandé pour rapidité)
url = f"{proxy_url}/api/assets/{asset_id}/thumbnail?size=preview"

# Pour original (meilleure précision)
url = f"{proxy_url}/api/assets/{asset_id}/original"

response = requests.get(url, headers={'x-api-key': api_key})
```

### JavaScript - Récupérer un thumbnail
```javascript
const response = await fetch(
  `/api/assets/${assetId}/thumbnail?size=preview`,
  { headers: { 'x-api-key': apiKey } }
);
```

## Endpoints qui NE fonctionnent PAS

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

## Recommandations pour Caption Maker

- **Pour l'affichage web** : Utiliser `thumbnail?size=preview`
- **Pour la détection de doublons** : Utiliser `/original` ou `thumbnail?size=fullsize`
- **Pour les miniatures de galerie** : Utiliser `thumbnail?size=thumbnail`

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