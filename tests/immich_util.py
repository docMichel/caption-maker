def get_immich_asset_path(asset_id):
    """Obtenir le chemin physique d'un asset Immich"""
    # Adapter selon votre configuration Immich
    # Généralement : /path/to/immich/upload/library/user-id/year/month/asset-id.ext
    
    # Ou utiliser l'API Immich pour récupérer le chemin
    metadata = get_immich_asset_metadata(asset_id)
    return metadata['originalPath']

def get_immich_asset_metadata(asset_id):
    """Récupérer les métadonnées depuis Immich"""
    response = requests.get(
        f"{IMMICH_API_URL}/api/assets/{asset_id}",
        headers={'x-api-key': IMMICH_API_KEY}
    )
    return response.json()