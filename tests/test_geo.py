    # test_geo.py
#!/usr/bin/env python3

import sys
sys.path.append('.')  # Pour trouver src

from src.services.geo_service import GeoService
import logging

# Activer les logs
logging.basicConfig(level=logging.INFO)

# Config DB
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'mysqlroot',
    'database': 'immich_gallery',
    'charset': 'utf8mb4'
}

# Créer le service
geo = GeoService(db_config)

# Tester différentes coordonnées
test_coords = [
    (-20.4501, 164.2135, "Tiébaghi, NC"),
    (-22.2758, 166.4581, "Nouméa, NC"),
    (48.8566, 2.3522, "Paris, France"),
    (13.4125, 103.8667, "Angkor Wat, Cambodge"),
]

for lat, lon, desc in test_coords:
    print(f"\n{'='*50}")
    print(f"Test: {desc}")
    result = geo.get_location_info(lat, lon)
    print(f"Adresse: {result.formatted_address}")
    print(f"Confiance: {result.confidence_score}")
    print(f"Sources: {result.data_sources}")