# src/data_import/country_detector.py
import requests
import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)

from typing import Optional

class CountryDetector:
    """Détecter le pays depuis des coordonnées GPS"""
    def detect_country(self, lat: float, lon: float) -> Optional[str]:
    
        """Détecter le code pays/territoire pour import GeoNames"""
    
        # Mapping complet des territoires qui ont leur propre fichier sur GeoNames
        TERRITORY_MAPPING = {
            # France
            'FR': {
                'Nouvelle-Calédonie|New Caledonia': 'NC',
                'Polynésie française|French Polynesia': 'PF',
                'Wallis-et-Futuna|Wallis and Futuna': 'WF',
                'Guadeloupe': 'GP',
                'Martinique': 'MQ',
                'Réunion|Reunion': 'RE',
                'Mayotte': 'YT',
                'Guyane française|French Guiana': 'GF',
                'Saint-Pierre-et-Miquelon': 'PM',
                'Saint-Barthélemy': 'BL',
                'Saint-Martin': 'MF'
            },
            # Pays-Bas
            'NL': {
                'Aruba': 'AW',
                'Curaçao|Curacao': 'CW',
                'Sint Maarten': 'SX',
                'Bonaire': 'BQ'
            },
            # Royaume-Uni
            'GB': {
                'Gibraltar': 'GI',
                'Bermuda': 'BM',
                'Cayman Islands': 'KY',
                'Turks and Caicos': 'TC',
                'British Virgin Islands': 'VG',
                'Anguilla': 'AI',
                'Montserrat': 'MS',
                'Falkland Islands': 'FK',
                'Jersey': 'JE',
                'Guernsey': 'GG',
                'Isle of Man': 'IM'
            },
            # États-Unis (certains territoires)
            'US': {
                'Puerto Rico': 'PR',
                'Virgin Islands': 'VI',
                'Guam': 'GU',
                'American Samoa': 'AS',
                'Northern Mariana': 'MP'
            },
            # Danemark
            'DK': {
                'Faroe Islands|Færøerne': 'FO',
                'Greenland|Grønland': 'GL'
            },
            # Norvège
            'NO': {
                'Svalbard': 'SJ'
            },
            # Finlande
            'FI': {
                'Åland|Aland': 'AX'
            },
            # Australie
            'AU': {
                'Norfolk Island': 'NF',
                'Christmas Island': 'CX',
                'Cocos Islands': 'CC'
            },
            # Nouvelle-Zélande
            'NZ': {
                'Cook Islands': 'CK',
                'Niue': 'NU',
                'Tokelau': 'TK'
            }
        }
    
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            params = {
                'lat': lat,
                'lon': lon,
                'format': 'json',
                'addressdetails': 1,
                'namedetails': 1,
                'accept-language': 'en,fr'
            }
            headers = {'User-Agent': 'ImmichGallery/1.0'}
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            address = data.get('address', {})
            country_code = address.get('country_code', '').upper()
            
            # Si le pays a des territoires spéciaux
            if country_code in TERRITORY_MAPPING:
                # Construire le texte de recherche
                search_text = ' '.join([
                    data.get('display_name', ''),
                    address.get('state', ''),
                    address.get('region', ''),
                    address.get('county', ''),
                    address.get('archipelago', ''),
                    address.get('island', '')
                ]).lower()
                
                # Vérifier chaque territoire
                for territory_names, territory_code in TERRITORY_MAPPING[country_code].items():
                    for name in territory_names.split('|'):
                        if name.lower() in search_text:
                            logger.info(f"Territoire détecté: {territory_code} ({name})")
                            return territory_code
            
            # Retourner le code pays standard
            logger.info(f"Pays détecté: {country_code}")
            return country_code if country_code else None
            
        except Exception as e:
            logger.error(f"Erreur détection pays: {e}")
            return None