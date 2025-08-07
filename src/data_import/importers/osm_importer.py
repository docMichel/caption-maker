# src/data_import/importers/osm_importer.py
import logging
import requests
import mysql.connector
import json
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class OSMImporter:
    def __init__(self, db_config):
        self.db_config = db_config
        self.overpass_url = "https://overpass-api.de/api/interpreter"
        
    def import_country(self, country_code: str) -> int:
        """Importer les POIs intéressants depuis OSM/Overpass"""
        logger.info(f"📥 Import POIs OSM pour {country_code}")
        
        # Mapping des codes pays vers les noms OSM
        country_names = {
            'NC': 'New Caledonia',
            'FR': 'France',
            'ID': 'Indonesia',
            'TH': 'Thailand',
            # Ajouter d'autres...
        }
        
        country_name = country_names.get(country_code, country_code)
        if country_code in ['NC', 'PF', 'WF']:
            query = f"""
            [out:json][timeout:90];
            area["ISO3166-1"="{country_code}"];
            (
            node["name"](area);
            way["name"](area);
            );
            out center 100;
        """
        else:

        # Requête Overpass pour récupérer les POIs importants
            query = f"""
            [out:json][timeout:60];
            area["ISO3166-1"="{country_code}"]["admin_level"="2"];
            (
            node["tourism"](area);
            way["tourism"](area);
            node["historic"](area);
            way["historic"](area);
            );
            out center;
            """
        
        try:
            # Exécuter la requête
            response = requests.post(
                self.overpass_url,
                data={'data': query},
                timeout=90
            )
            response.raise_for_status()
            
            data = response.json()
            elements = data.get('elements', [])
            
            logger.info(f"   {len(elements)} POIs trouvés sur OSM")
            
            # Insérer dans la base
            return self._insert_pois(elements, country_code)
            
        except Exception as e:
            logger.error(f"❌ Erreur import OSM: {e}")
            return 0
    
    def _insert_pois(self, elements: List[Dict], country_code: str) -> int:
        """Insérer les POIs dans la base"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            insert_query = """
                INSERT INTO osm_pois 
                (id, name, latitude, longitude, country_code, 
                 osm_type, osm_key, osm_value, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    tags = VALUES(tags)
            """
            
            count = 0
            batch = []
            
            for element in elements:
                poi_data = self._extract_poi_data(element, country_code)
                if poi_data:
                    batch.append(poi_data)
                    
                    if len(batch) >= 100:
                        cursor.executemany(insert_query, batch)
                        count += len(batch)
                        batch = []
                        conn.commit()
            
            # Insérer le reste
            if batch:
                cursor.executemany(insert_query, batch)
                count += len(batch)
                conn.commit()
            
            logger.info(f"   ✅ {count} POIs importés")
            return count
            
        finally:
            cursor.close()
            conn.close()
    
    def _extract_poi_data(self, element: Dict, country_code: str) -> Optional[tuple]:
        """Extraire les données d'un POI OSM"""
        tags = element.get('tags', {})
        
        # Nom du POI
        name = (tags.get('name') or 
                tags.get('name:fr') or 
                tags.get('name:en'))
        
        if not name:
            return None
        
        # Coordonnées
        if element['type'] == 'node':
            lat = element['lat']
            lon = element['lon']
        else:  # way ou relation
            center = element.get('center', {})
            lat = center.get('lat')
            lon = center.get('lon')
            if not lat or not lon:
                return None
        
        # Déterminer le type principal
        osm_key = None
        osm_value = None
        
        for key in ['tourism', 'historic', 'natural', 'amenity']:
            if key in tags:
                osm_key = key
                osm_value = tags[key]
                break
        
        # Tags importants à conserver
        important_tags = {
            k: v for k, v in tags.items() 
            if k in ['tourism', 'historic', 'natural', 'amenity', 
                    'website', 'wikipedia', 'opening_hours', 
                    'fee', 'description', 'architect', 'year']
        }
        
        return (
            element['id'],
            name,
            lat,
            lon,
            country_code,
            element['type'],
            osm_key,
            osm_value,
            json.dumps(important_tags, ensure_ascii=False)
        )