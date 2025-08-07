# src/data_import/country_detector.py
import requests
from typing import Optional

class CountryDetector:
    """Détecter le pays depuis des coordonnées GPS"""
    
    def detect_country(self, lat: float, lon: float) -> Optional[str]:
        """Utilise Nominatim pour détecter le pays"""
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                'lat': lat,
                'lon': lon,
                'format': 'json',
                'zoom': 3  # Niveau pays
            }
            headers = {'User-Agent': 'ImmichGallery/1.0'}
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            data = response.json()
            
            # Extraire le code pays
            address = data.get('address', {})
            country_code = address.get('country_code', '').upper()
            
            return country_code if country_code else None
            
        except Exception as e:
            return None