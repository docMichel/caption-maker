#!/usr/bin/env python3
"""
📍 src/services/geo_service.py

GeoService - Service de géolocalisation intelligent
Exploite TOUTES les données disponibles avec fallback gracieux
"""

import mysql.connector
import requests
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import hashlib

logger = logging.getLogger(__name__)

# Import de ImportManager
try:
    import sys
    import os
    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    
    from data_import.import_manager import ImportManager
    IMPORT_MANAGER_AVAILABLE = True
    logger.info("✅ ImportManager chargé")
except ImportError as e:
    IMPORT_MANAGER_AVAILABLE = False
    logger.warning(f"⚠️ ImportManager non disponible: {e}")

@dataclass
class GeoLocation:
    """Structure unifiée pour les données de géolocalisation"""
    latitude: float
    longitude: float
    
    # Informations administratives
    formatted_address: str = ""
    city: str = ""
    region: str = ""
    country: str = ""
    country_code: str = ""
    
    # Sites d'intérêt
    unesco_sites: List[Dict] = None
    cultural_sites: List[Dict] = None
    nearby_pois: List[Dict] = None
    major_cities: List[Dict] = None
    osm_pois: List[Dict] = None
    geonames_all: List[Dict] = None
    
    # Métadonnées
    confidence_score: float = 0.0
    data_sources: List[str] = None
    search_radius_km: float = 10.0
    
    def __post_init__(self):
        """Initialiser les listes vides"""
        if self.unesco_sites is None:
            self.unesco_sites = []
        if self.cultural_sites is None:
            self.cultural_sites = []
        if self.nearby_pois is None:
            self.nearby_pois = []
        if self.major_cities is None:
            self.major_cities = []
        if self.osm_pois is None:
            self.osm_pois = []
        if self.geonames_all is None:
            self.geonames_all = []
        if self.data_sources is None:
            self.data_sources = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir en dictionnaire pour JSON/API"""
        return asdict(self)

class GeoService:
    """
    Service de géolocalisation multi-sources avec exploitation maximale
    """
    
    def __init__(self, db_config: Dict[str, str], cache_ttl: int = 3600):
        self.db_config = db_config
        self.cache_ttl = cache_ttl
        self.connection = None
        self.cursor = None
        
        # Cache en mémoire
        self._cache = {}
        
        # Configuration APIs externes
        self.nominatim_config = {
            'base_url': 'https://nominatim.openstreetmap.org',
            'headers': {'User-Agent': 'ImmichCaptionGenerator/1.0'},
            'timeout': 10,
            'rate_limit': 1.1
        }
        
        self.overpass_config = {
            'base_url': 'https://overpass-api.de/api/interpreter',
            'timeout': 15,
            'max_pois': 10
        }
        
        self._last_external_request = 0
        
        logger.info("🌍 GeoService initialisé")
    
    def connect_db(self):
        """Établir la connexion MySQL"""
        try:
            self.connection = mysql.connector.connect(**self.db_config)
            self.cursor = self.connection.cursor(dictionary=True)
            logger.debug("✅ Connexion MySQL établie")
        except mysql.connector.Error as e:
            logger.error(f"❌ Erreur connexion MySQL: {e}")
            raise
    
    def disconnect_db(self):
        """Fermer la connexion MySQL"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.debug("🔌 Connexion MySQL fermée")
    
    def _get_cache_key(self, lat: float, lon: float, radius: float) -> str:
        """Générer une clé de cache unique"""
        key_string = f"{lat:.6f},{lon:.6f},{radius}"
        return hashlib.md5(key_string.encode()).hexdigest()[:16]
    
    def _is_cache_valid(self, timestamp: float) -> bool:
        """Vérifier si l'entrée de cache est encore valide"""
        return time.time() - timestamp < self.cache_ttl
    
    def _respect_rate_limit(self):
        """Respecter les limites de taux des APIs externes"""
        elapsed = time.time() - self._last_external_request
        if elapsed < self.nominatim_config['rate_limit']:
            sleep_time = self.nominatim_config['rate_limit'] - elapsed
            logger.debug(f"⏱️ Rate limit: attente {sleep_time:.1f}s")
            time.sleep(sleep_time)
        self._last_external_request = time.time()
    
    def get_location_info(self, latitude: float, longitude: float, 
                         radius_km: float = 10.0) -> GeoLocation:
        """
        Point d'entrée principal - Exploite TOUTES les sources disponibles
        """
        # Validation
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError(f"Coordonnées invalides: {latitude}, {longitude}")
        
        # Cache
        cache_key = self._get_cache_key(latitude, longitude, radius_km)
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                logger.info(f"📍 Cache hit pour {latitude:.4f},{longitude:.4f}")
                return cached_data
        
        logger.info(f"🌍 Géolocalisation pour {latitude:.4f},{longitude:.4f} (rayon {radius_km}km)")
        
        # Import automatique des données si nécessaire
        if IMPORT_MANAGER_AVAILABLE:
            try:
                import_manager = ImportManager(self.db_config)
                country_code = import_manager.ensure_data_for_location(latitude, longitude)
                logger.info(f"📍 Pays détecté: {country_code}")
            except Exception as e:
                logger.warning(f"⚠️ Import auto échoué: {e}")
                import traceback
                traceback.print_exc()

        
        # Initialiser le résultat
        location = GeoLocation(
            latitude=latitude,
            longitude=longitude,
            search_radius_km=radius_km
        )
        
        try:
            self.connect_db()
            
            # === 1. GEONAMES - Notre base principale ===
            logger.info("📍 Recherche GeoNames...")
            try:
                # Récupérer TOUT ce qu'on peut de GeoNames
                location.geonames_all = self._search_all_geonames(latitude, longitude, radius_km)
                
                if location.geonames_all:
                    logger.info(f"   ✅ {len(location.geonames_all)} entrées GeoNames trouvées")
                    
                    # Analyser et catégoriser
                    for entry in location.geonames_all:
                        feature_class = entry.get('feature_class', '')
                        feature_code = entry.get('feature_code', '')
                        
                        # Villes et lieux habités
                        if feature_class == 'P':
                            if len(location.major_cities) < 10:
                                location.major_cities.append(entry)
                        
                        # Sites potentiellement culturels
                        elif feature_code in ['MUS', 'MNMT', 'HSTS', 'RUIN', 'CSTL', 
                                            'PAL', 'CH', 'MSQE', 'TMPL', 'SHRN']:
                            location.cultural_sites.append(entry)
                        
                        # POIs naturels ou autres
                        elif feature_class in ['T', 'H', 'L', 'S']:
                            location.nearby_pois.append(entry)
                    
                    # Extraire la ville principale
                    if location.major_cities:
                        closest_city = location.major_cities[0]
                        location.city = closest_city['name']
                        location.country_code = closest_city.get('country_code', '')
                        location.confidence_score += 0.4
                        location.data_sources.append('geonames')
                        
                        logger.info(f"   📍 Ville principale: {location.city} "
                                  f"({closest_city['distance_km']:.1f}km)")
                    
                    if location.cultural_sites:
                        logger.info(f"   🏛️ {len(location.cultural_sites)} sites culturels GeoNames")
                else:
                    logger.info("   ℹ️ Aucune donnée GeoNames")
                    
            except Exception as e:
                logger.warning(f"   ⚠️ Erreur GeoNames: {e}")
            
            # === 2. UNESCO - Sites patrimoniaux ===
            logger.info("🏛️ Recherche UNESCO...")
            try:
                location.unesco_sites = self._search_unesco_sites(latitude, longitude, radius_km * 2)
                if location.unesco_sites:
                    location.data_sources.append('unesco')
                    location.confidence_score += 0.3
                    logger.info(f"   ✅ {len(location.unesco_sites)} sites UNESCO")
                    for site in location.unesco_sites[:2]:
                        logger.info(f"      - {site['name']} ({site['distance_km']:.1f}km)")
                else:
                    logger.info("   ℹ️ Aucun site UNESCO proche")
            except Exception as e:
                logger.debug(f"   ⚠️ Table UNESCO non disponible: {e}")
            
            # === 3. CULTURAL SITES - Sites culturels extraits ===
            logger.info("🎭 Recherche sites culturels...")
            try:
                cultural_db = self._search_cultural_sites(latitude, longitude, radius_km)
                if cultural_db:
                    # Fusionner avec ceux de GeoNames
                    for site in cultural_db:
                        if site not in location.cultural_sites:
                            location.cultural_sites.append(site)
                    location.data_sources.append('cultural_db')
                    location.confidence_score += 0.2
                    logger.info(f"   ✅ {len(cultural_db)} sites culturels DB")
            except Exception as e:
                logger.debug(f"   ⚠️ Table cultural_sites non disponible: {e}")
            
            # === 4. OSM POIs - Points d'intérêt OpenStreetMap ===
            logger.info("🗺️ Recherche POIs OSM...")
            try:
                location.osm_pois = self._search_osm_pois(latitude, longitude, radius_km)
                if location.osm_pois:
                    location.data_sources.append('osm_db')
                    location.confidence_score += 0.2
                    logger.info(f"   ✅ {len(location.osm_pois)} POIs OSM")
                    for poi in location.osm_pois[:3]:
                        logger.info(f"      - {poi['name']} ({poi['osm_value']}, "
                                  f"{poi['distance_km']:.1f}km)")
            except Exception as e:
                logger.debug(f"   ⚠️ Table osm_pois non disponible: {e}")
            
            # === 5. NOMINATIM - Pour enrichir (pas remplacer) ===
            if location.confidence_score < 0.8 or not location.formatted_address:
                logger.info("🌐 Enrichissement Nominatim...")
                try:
                    nominatim_data = self._get_nominatim_data(latitude, longitude)
                    if nominatim_data:
                        self._merge_nominatim_data(location, nominatim_data)
                        location.data_sources.append('nominatim')
                        location.confidence_score = min(location.confidence_score + 0.2, 1.0)
                        logger.info(f"   ✅ Adresse enrichie: {location.formatted_address}")
                except Exception as e:
                    logger.warning(f"   ⚠️ Erreur Nominatim: {e}")
            
            # === 6. OVERPASS API - Si on manque encore de POIs ===
            if len(location.nearby_pois) < 5 and location.confidence_score < 0.9:
                logger.info("🔍 Recherche POIs Overpass en ligne...")
                try:
                    overpass_pois = self._search_nearby_pois(latitude, longitude, radius_km / 2)
                    if overpass_pois:
                        location.nearby_pois.extend(overpass_pois)
                        location.data_sources.append('overpass_api')
                        location.confidence_score += 0.1
                        logger.info(f"   ✅ {len(overpass_pois)} POIs Overpass")
                except Exception as e:
                    logger.debug(f"   ⚠️ Overpass non disponible: {e}")
            
            # === 7. FINALISATION ===
            self._finalize_location_data(location)
            
        except Exception as e:
            logger.error(f"❌ Erreur géolocalisation: {e}")
            # Fallback minimal
            location.formatted_address = f"{latitude:.4f}, {longitude:.4f}"
            location.confidence_score = 0.1
        finally:
            self.disconnect_db()
        
        # Cache et retour
        self._cache[cache_key] = (location, time.time())
        
        # Log final détaillé
        logger.info(f"🎯 Géolocalisation terminée:")
        logger.info(f"   📍 Adresse: {location.formatted_address}")
        logger.info(f"   🏙️ Ville: {location.city or 'Non déterminée'}")
        logger.info(f"   🌍 Pays: {location.country_code or 'Non déterminé'}")
        logger.info(f"   📊 Score confiance: {location.confidence_score:.2f}")
        logger.info(f"   🗂️ Sources utilisées: {', '.join(location.data_sources)}")
        logger.info(f"   📈 Données collectées:")
        logger.info(f"      - Villes: {len(location.major_cities)}")
        logger.info(f"      - UNESCO: {len(location.unesco_sites)}")
        logger.info(f"      - Culturel: {len(location.cultural_sites)}")
        logger.info(f"      - POIs: {len(location.nearby_pois)}")
        logger.info(f"      - OSM: {len(location.osm_pois)}")
        
        return location
    
    def _search_all_geonames(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Récupérer TOUTES les données GeoNames dans le rayon"""
        query = """
            SELECT 
                geonameid as id,
                name,
                asciiname,
                latitude,
                longitude,
                feature_class,
                feature_code,
                country_code,
                cc2,
                admin1_code,
                admin2_code,
                population,
                elevation,
                timezone,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM geonames 
            WHERE haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY 
                CASE 
                    WHEN feature_class = 'P' THEN population * 1000 / (distance_km + 1)
                    ELSE 1 / (distance_km + 0.1)
                END DESC
            LIMIT 100
        """
        
        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        results = self.cursor.fetchall()
        
        # Enrichir chaque résultat
        for result in results:
            result['source'] = 'geonames'
            result['type'] = self._get_feature_description(
                result['feature_class'], 
                result['feature_code']
            )
        
        return results
    
    def _get_feature_description(self, feature_class: str, feature_code: str) -> str:
        """Convertir les codes GeoNames en description lisible"""
        descriptions = {
            # Places
            'PPL': 'ville',
            'PPLA': 'capitale administrative',
            'PPLA2': 'chef-lieu région',
            'PPLA3': 'chef-lieu département',
            'PPLC': 'capitale',
            'PPLS': 'villages',
            
            # Hydrographic
            'BAY': 'baie',
            'BCH': 'plage',
            'CAPE': 'cap',
            'COVE': 'anse',
            'LK': 'lac',
            'STM': 'rivière',
            'SPNG': 'source',
            'WTRF': 'cascade',
            
            # Terrain
            'MT': 'montagne',
            'MTS': 'montagnes',
            'PK': 'pic',
            'VLC': 'volcan',
            'ISL': 'île',
            'ISLS': 'îles',
            'PASS': 'col',
            'VAL': 'vallée',
            
            # Cultural
            'MUS': 'musée',
            'MNMT': 'monument',
            'HSTS': 'site historique',
            'RUIN': 'ruines',
            'CSTL': 'château',
            'PAL': 'palais',
            'CH': 'église',
            'MSQE': 'mosquée',
            'TMPL': 'temple',
            'SHRN': 'sanctuaire',
            'TOWR': 'tour',
            'ARCH': 'arc',
            'GDN': 'jardin',
            
            # Infrastructure
            'AIRP': 'aéroport',
            'PORT': 'port',
            'BLDG': 'bâtiment',
            'BDG': 'pont',
            'UNIV': 'université',
            'SCH': 'école',
            'HSPD': 'hôpital',
            'MKT': 'marché',
            'MALL': 'centre commercial'
        }
        
        return descriptions.get(feature_code, feature_class.lower())
    
    def _search_unesco_sites(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher les sites UNESCO"""
        query = """
            SELECT 
                id, name, latitude, longitude, country_code, category,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM unesco_sites 
            WHERE haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY distance_km ASC
            LIMIT 10
        """
        
        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        sites = self.cursor.fetchall()
        
        for site in sites:
            site['relevance_score'] = self._calculate_site_relevance(site, 'unesco')
            site['source'] = 'unesco'
        
        return sites
    
    def _search_cultural_sites(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher les sites culturels dans la DB dédiée"""
        query = """
            SELECT 
                id, name, latitude, longitude, country_code, 
                feature_code, site_type,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM cultural_sites 
            WHERE haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY distance_km ASC
            LIMIT 20
        """
        logger.debug(f"   Requête cultural_sites avec rayon {radius_km}km")

        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        sites = self.cursor.fetchall()
        logger.debug(f"   Trouvé {len(sites)} sites culturels dans la DB")

        for site in sites:
            site['relevance_score'] = self._calculate_site_relevance(site, 'cultural')
            site['source'] = 'cultural_db'
        
        return sites
    
    def _search_osm_pois(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher les POIs OSM importés"""
        query = """
            SELECT 
                id,
                name,
                latitude,
                longitude,
                osm_type,
                osm_key,
                osm_value,
                tags,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM osm_pois
            WHERE haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY 
                CASE osm_key
                    WHEN 'tourism' THEN 1
                    WHEN 'historic' THEN 2
                    WHEN 'amenity' THEN 3
                    ELSE 4
                END,
                distance_km ASC
            LIMIT 20
        """
        
        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        pois = self.cursor.fetchall()
        
        # Parser les tags JSON et enrichir
        for poi in pois:
            if poi.get('tags'):
                try:
                    poi['tags'] = json.loads(poi['tags'])
                except:
                    poi['tags'] = {}
            poi['source'] = 'osm'
            poi['type'] = f"{poi['osm_key']}={poi['osm_value']}"
        
        return pois
    
    def _search_major_cities(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher spécifiquement les villes importantes"""
        query = """
            SELECT 
                geonameid as id, 
                name, 
                asciiname as ascii_name, 
                latitude, 
                longitude, 
                country_code,
                admin1_code,
                admin2_code,
                population,
                feature_code,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM geonames 
            WHERE feature_class = 'P' 
            AND haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY 
                population * 1000 / (distance_km + 1) DESC
            LIMIT 10
        """
        
        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        cities = self.cursor.fetchall()
        
        for city in cities:
            city['source'] = 'geonames'
            city['type'] = self._get_city_type(city.get('feature_code', 'PPL'))
        
        return cities
    
    def _calculate_site_relevance(self, site: Dict, site_type: str) -> float:
        """Calculer un score de pertinence pour un site"""
        relevance = 1.0
        distance_km = float(site.get('distance_km', 999))
        
        # UNESCO = top pertinence
        if site_type == 'unesco':
            relevance += 1.0
        elif site_type == 'cultural':
            feature_code = site.get('feature_code', '')
            if feature_code in ['HSTS', 'MUS', 'MNMT']:
                relevance += 0.7
            elif feature_code in ['TMPL', 'PAL', 'CSTL']:
                relevance += 0.6
            else:
                relevance += 0.4
        
        # Bonus proximité
        if distance_km < 1:
            relevance += 0.5
        elif distance_km < 5:
            relevance += 0.3
        elif distance_km < 10:
            relevance += 0.1
        else:
            relevance -= distance_km * 0.02
        
        return max(0.1, min(2.0, relevance))
    
    def _get_city_type(self, feature_code: str) -> str:
        """Type de ville selon le code GeoNames"""
        city_types = {
            'PPLC': 'capitale',
            'PPLA': 'centre_administratif', 
            'PPLA2': 'chef_lieu_region',
            'PPLA3': 'chef_lieu_district',
            'PPLA4': 'chef_lieu_commune',
            'PPLS': 'villages',
            'PPL': 'ville'
        }
        return city_types.get(feature_code, 'localite')
    
    def _get_nominatim_data(self, lat: float, lon: float) -> Optional[Dict]:
        """Récupérer les données Nominatim pour enrichissement"""
        try:
            self._respect_rate_limit()
            
            url = f"{self.nominatim_config['base_url']}/reverse"
            params = {
                'lat': lat,
                'lon': lon,
                'format': 'json',
                'addressdetails': 1,
                'extratags': 1,
                'namedetails': 1,
                'zoom': 18,
                'accept-language': 'fr,en'
            }
            
            logger.debug(f"   🌐 Appel Nominatim: {lat:.4f}, {lon:.4f}")
            
            response = requests.get(
                url,
                params=params,
                headers=self.nominatim_config['headers'],
                timeout=self.nominatim_config['timeout']
            )
            response.raise_for_status()
            
            data = response.json()
            if 'error' not in data:
                logger.debug(f"   ✅ Nominatim OK: {data.get('display_name', '')[:50]}...")
                return data
            else:
                logger.warning(f"   ⚠️ Nominatim erreur: {data.get('error')}")
                return None
                
        except requests.RequestException as e:
            logger.warning(f"   ⚠️ Erreur Nominatim: {e}")
            return None
    
    def _search_nearby_pois(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher des POIs via Overpass API (online)"""
        try:
            self._respect_rate_limit()
            
            radius_m = int(radius_km * 1000)
            
            # Requête Overpass optimisée
            query = f"""
            [out:json][timeout:10];
            (
              node["tourism"~"attraction|museum|monument|viewpoint|gallery"](around:{radius_m},{lat},{lon});
              node["historic"](around:{radius_m},{lat},{lon});
              node["natural"~"peak|beach|bay|cape|waterfall|volcano"](around:{radius_m},{lat},{lon});
              node["amenity"~"place_of_worship"]["name"](around:{radius_m},{lat},{lon});
            );
            out body qt 20;
            """
            
            logger.debug(f"   🔍 Requête Overpass (rayon {radius_m}m)")
            
            response = requests.post(
                self.overpass_config['base_url'],
                data={'data': query},
                timeout=self.overpass_config['timeout']
            )
            response.raise_for_status()
            
            data = response.json()
            elements = data.get('elements', [])
            
            logger.debug(f"   ✅ Overpass: {len(elements)} POIs trouvés")
            
            # Traiter les POIs
            pois = []
            for element in elements[:self.overpass_config['max_pois']]:
                poi = self._process_overpass_poi(element, lat, lon)
                if poi:
                    pois.append(poi)
            
            # Trier par pertinence
            pois.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            return pois[:5]
            
        except requests.RequestException as e:
            logger.warning(f"   ⚠️ Erreur Overpass: {e}")
            return []
    
    def _process_overpass_poi(self, element: Dict, ref_lat: float, ref_lon: float) -> Optional[Dict]:
        """Traiter un POI Overpass"""
        tags = element.get('tags', {})
        poi_lat = element.get('lat', 0)
        poi_lon = element.get('lon', 0)
        
        # Nom du POI (multilingue)
        name = (tags.get('name') or 
                tags.get('name:fr') or 
                tags.get('name:en') or 
                tags.get('int_name'))
        
        if not name or name in ['yes', 'no']:
            return None
        
        # Type principal
        poi_type = None
        for key in ['tourism', 'historic', 'natural', 'amenity']:
            if key in tags:
                poi_type = f"{key}={tags[key]}"
                break
        
        # Distance
        distance_m = self._haversine_distance(ref_lat, ref_lon, poi_lat, poi_lon) * 1000
        
        # Score de pertinence
        relevance = 1.0
        if tags.get('tourism') in ['attraction', 'museum', 'monument']:
            relevance += 0.7
        if tags.get('historic'):
            relevance += 0.6
        if tags.get('natural') in ['peak', 'volcano', 'waterfall']:
            relevance += 0.5
        if 'wikipedia' in tags or 'wikidata' in tags:
            relevance += 0.3
        
        # Malus distance
        relevance -= distance_m / 10000
        
        return {
            'name': name,
            'type': poi_type,
            'latitude': poi_lat,
            'longitude': poi_lon,
            'distance_m': int(distance_m),
            'distance_km': distance_m / 1000,
            'relevance_score': max(0.1, relevance),
            'source': 'overpass_api',
            'tags': {k: v for k, v in tags.items() 
                    if k in ['tourism', 'historic', 'natural', 'amenity',
                            'website', 'wikipedia', 'opening_hours', 'fee']}
        }
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Distance haversine en km"""
        from math import radians, cos, sin, asin, sqrt
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        return 6371 * c
    
    def _merge_nominatim_data(self, location: GeoLocation, nominatim_data: Dict):
        """Enrichir avec les données Nominatim"""
        address = nominatim_data.get('address', {})
        
        # Adresse complète
        location.formatted_address = nominatim_data.get('display_name', '')
        
        # Détails administratifs
        if not location.city:
            location.city = (address.get('city') or 
                           address.get('town') or 
                           address.get('village') or 
                           address.get('hamlet') or
                           address.get('municipality', ''))
        
        if not location.region:
            location.region = (address.get('state') or 
                             address.get('region') or 
                             address.get('province', ''))
        
        if not location.country:
            location.country = address.get('country', '')
        
        if not location.country_code:
            location.country_code = address.get('country_code', '').upper()
        
        # Extra tags intéressants
        extratags = nominatim_data.get('extratags', {})
        if 'place' in extratags:
            logger.debug(f"   📍 Type de lieu Nominatim: {extratags['place']}")
    
    def _finalize_location_data(self, location: GeoLocation):
        """Finaliser et optimiser les données collectées"""
        logger.debug("🔧 Finalisation des données...")
        
        # Générer une adresse intelligente si pas déjà fait
        if not location.formatted_address:
            parts = []
            
            # Priorité 1: Site UNESCO
            if location.unesco_sites:
                parts.append(location.unesco_sites[0]['name'])
            # Priorité 2: Site culturel majeur
            elif location.cultural_sites:
                parts.append(location.cultural_sites[0]['name'])
            
            # Ajouter la ville
            if location.city:
                parts.append(location.city)
            
            # Ajouter la région si différente de la ville
            if location.region and location.region != location.city:
                parts.append(location.region)
            
            # Ajouter le pays
            if location.country:
                parts.append(location.country)
            
            location.formatted_address = ', '.join(parts) if parts else f"{location.latitude:.4f}, {location.longitude:.4f}"
        
        # Limiter la longueur
        if len(location.formatted_address) > 150:
            # Version courte
            if location.city and location.country:
                location.formatted_address = f"{location.city}, {location.country}"
            else:
                location.formatted_address = location.formatted_address[:147] + "..."
        
        # Dédupliquer les listes
        location.cultural_sites = self._deduplicate_sites(location.cultural_sites)
        location.nearby_pois = self._deduplicate_sites(location.nearby_pois)
        
        logger.debug(f"   ✅ Adresse finale: {location.formatted_address}")
    
    def _deduplicate_sites(self, sites: List[Dict]) -> List[Dict]:
        """Dédupliquer une liste de sites par nom"""
        seen = set()
        unique = []
        
        for site in sites:
            name = site.get('name', '')
            if name and name not in seen:
                seen.add(name)
                unique.append(site)
        
        return unique
    
    def get_location_summary_for_ai(self, location: GeoLocation) -> Dict[str, str]:
        """
        Générer un résumé riche pour l'IA de génération de légendes
        Exploite TOUTES les données collectées
        """
        summary = {
            'location_basic': '',
            'location_detailed': location.formatted_address,
            'cultural_context': '',
            'nearby_attractions': '',
            'geographic_context': '',
            'natural_features': '',
            'urban_context': '',
            'confidence_level': 'high' if location.confidence_score > 0.7 else 'medium' if location.confidence_score > 0.4 else 'low',
            'data_richness': ''
        }
        
        # Localisation basique
        if location.city:
            summary['location_basic'] = f"{location.city}"
            if location.country:
                summary['location_basic'] += f", {location.country}"
        else:
            summary['location_basic'] = location.formatted_address
        
        # Contexte culturel riche
        cultural_elements = []
        
        # UNESCO en premier
        if location.unesco_sites:
            for site in location.unesco_sites[:2]:
                cultural_elements.append(
                    f"Site UNESCO '{site['name']}' à {site['distance_km']:.1f}km"
                )
        
        # Sites culturels
        if location.cultural_sites:
            for site in location.cultural_sites[:3]:
                site_type = site.get('type', site.get('site_type', 'site'))
                cultural_elements.append(
                    f"{site_type.title()}: {site['name']}"
                )
        
        if cultural_elements:
            summary['cultural_context'] = '; '.join(cultural_elements)
        
        # Attractions et POIs
        attractions = []
        
        # POIs OSM
        if location.osm_pois:
            for poi in location.osm_pois[:3]:
                poi_type = poi.get('osm_value', poi.get('type', 'lieu'))
                attractions.append(f"{poi['name']} ({poi_type})")
        
        # POIs généraux
        if location.nearby_pois:
            for poi in location.nearby_pois[:3]:
                if poi.get('name') not in [a.split(' (')[0] for a in attractions]:
                    attractions.append(poi['name'])
        
        if attractions:
            summary['nearby_attractions'] = ', '.join(attractions[:5])
        
        # Contexte géographique
        geo_elements = []
        
        # Villes proches
        if location.major_cities and len(location.major_cities) > 1:
            nearby = location.major_cities[1]
            geo_elements.append(
                f"Près de {nearby['name']} ({nearby['distance_km']:.0f}km)"
            )
        
        # Région
        if location.region:
            geo_elements.append(f"Région: {location.region}")
        
        if geo_elements:
            summary['geographic_context'] = ', '.join(geo_elements)
        
        # Éléments naturels
        natural = []
        for entry in location.geonames_all:
            if entry.get('feature_class') in ['T', 'H', 'L']:
                feature_type = entry.get('type', '')
                if feature_type in ['montagne', 'pic', 'volcan', 'plage', 'baie', 
                                  'cap', 'île', 'lac', 'rivière', 'cascade']:
                    natural.append(f"{entry['name']} ({feature_type})")
        
        if natural:
            summary['natural_features'] = ', '.join(natural[:3])
        
        # Contexte urbain
        if location.major_cities:
            main_city = location.major_cities[0]
            pop = main_city.get('population', 0)
            if pop > 1000000:
                summary['urban_context'] = "Grande métropole"
            elif pop > 100000:
                summary['urban_context'] = "Ville importante"
            elif pop > 10000:
                summary['urban_context'] = "Ville moyenne"
            else:
                summary['urban_context'] = "Petite ville/village"
        
        # Richesse des données
        total_data = (len(location.unesco_sites) + 
                     len(location.cultural_sites) + 
                     len(location.nearby_pois) + 
                     len(location.osm_pois))
        
        if total_data > 20:
            summary['data_richness'] = "Très riche"
        elif total_data > 10:
            summary['data_richness'] = "Riche"
        elif total_data > 5:
            summary['data_richness'] = "Modérée"
        else:
            summary['data_richness'] = "Limitée"
        
        logger.info("🤖 Résumé pour IA généré:")
        for key, value in summary.items():
            if value:
                logger.debug(f"   {key}: {value}")
        
        return summary
    
    def clear_cache(self):
        """Vider le cache"""
        self._cache.clear()
        logger.info("🗑️ Cache vidé")