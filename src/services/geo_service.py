#!/usr/bin/env python3
"""
📍 src/services/geo_service.py

GeoService - Service de géolocalisation intelligent
Utilise les données MySQL importées + fallback APIs externes
Optimisé pour génération de légendes contextuelles
"""
import sys
import os

# Forcer le bon chemin
_current_dir = os.path.dirname(os.path.abspath(__file__))
_src_dir = os.path.dirname(_current_dir)
_root_dir = os.path.dirname(_src_dir)

# Ajouter dans l'ordre : root puis src
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Maintenant les imports normaux
import mysql.connector
import requests

import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import json
import hashlib

try:
    from data_import import ImportManager
    IMPORT_MANAGER_AVAILABLE = True
    print(f"✅ ImportManager chargé depuis {_src_dir}")
except ImportError as e:
    IMPORT_MANAGER_AVAILABLE = False
    print(f"❌ ImportManager non disponible: {e}")
    print(f"   sys.path: {sys.path[:3]}")

logger = logging.getLogger(__name__)


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
        if self.data_sources is None:
            self.data_sources = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir en dictionnaire pour JSON/API"""
        return asdict(self)

class GeoService:
    """
    Service de géolocalisation intelligent multi-sources
    
    Sources de données (par ordre de priorité):
    1. UNESCO sites (base MySQL)
    2. Cultural sites (base MySQL) 
    3. GeoNames local (base MySQL)
    4. Nominatim (fallback externe, gratuit)
    5. Overpass API (POIs contextuels)
    """
    
    def __init__(self, db_config: Dict[str, str], cache_ttl: int = 3600):
        """
        Initialiser le service de géolocalisation
        
        Args:
            db_config: Configuration MySQL
            cache_ttl: Durée de vie du cache en secondes (défaut: 1h)
        """
        self.db_config = db_config
        self.cache_ttl = cache_ttl
        self.connection = None
        self.cursor = None
        
        # Cache en mémoire simple {cache_key: (data, timestamp)}
        self._cache = {}
        
        # Configuration des APIs externes
        self.nominatim_config = {
            'base_url': 'https://nominatim.openstreetmap.org',
            'headers': {'User-Agent': 'ImmichCaptionGenerator/1.0'},
            'timeout': 10,
            'rate_limit': 1.1  # secondes entre requêtes
        }
        
        self.overpass_config = {
            'base_url': 'https://overpass-api.de/api/interpreter',
            'timeout': 15,
            'max_pois': 5
        }
        
        # Dernière requête externe (pour rate limiting)
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
            time.sleep(sleep_time)
        self._last_external_request = time.time()
    
    def get_location_info(self, latitude: float, longitude: float, 
                         radius_km: float = 10.0) -> GeoLocation:
        """
        Point d'entrée principal pour la géolocalisation
        
        Args:
            latitude: Latitude GPS
            longitude: Longitude GPS  
            radius_km: Rayon de recherche en km
            
        Returns:
            GeoLocation avec toutes les données contextuelles
        """
        # Validation des coordonnées
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise ValueError(f"Coordonnées invalides: {latitude}, {longitude}")
        
        # Vérifier le cache
        cache_key = self._get_cache_key(latitude, longitude, radius_km)
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                logger.info(f"📍 Cache hit pour {latitude:.4f},{longitude:.4f}")
                return cached_data
        
        logger.info(f"🌍 Géolocalisation pour {latitude:.4f},{longitude:.4f} (rayon {radius_km}km)")
        if IMPORT_MANAGER_AVAILABLE:
            try:
                import_manager = ImportManager(self.db_config)
                country_code = import_manager.ensure_data_for_location(latitude, longitude)
                logger.info(f"📍 Pays détecté: {country_code}")
            except Exception as e:
                logger.warning(f"⚠️ Import automatique échoué: {e}")



        # Initialiser la structure de résultat
        location = GeoLocation(
            latitude=latitude,
            longitude=longitude,
            search_radius_km=radius_km
        )

        try:
            self.connect_db()
            
            # 1. Rechercher sites UNESCO proches
            try:
                location.unesco_sites = self._search_unesco_sites(latitude, longitude, radius_km)
                if location.unesco_sites:
                    location.data_sources.append('unesco_mysql')
                    location.confidence_score += 0.4
                    logger.info(f"   ✅ {len(location.unesco_sites)} sites UNESCO trouvés")
            except Exception as e:
                logger.warning(f"   ⚠️ Erreur recherche UNESCO: {e}")
            
            # 2. Rechercher sites culturels
            try:
                location.cultural_sites = self._search_cultural_sites(latitude, longitude, radius_km)
                if location.cultural_sites:
                    location.data_sources.append('cultural_mysql')
                    location.confidence_score += 0.3
                    logger.info(f"   ✅ {len(location.cultural_sites)} sites culturels trouvés")
            except Exception as e:
                logger.warning(f"   ⚠️ Erreur recherche culturelle: {e}")
            
            # 3. Rechercher villes importantes proches
            try:
                location.major_cities = self._search_major_cities(latitude, longitude, radius_km * 2)
                if location.major_cities:
                    location.data_sources.append('cities_mysql')
                    location.confidence_score += 0.2
                    closest_city = location.major_cities[0]
                    location.city = closest_city['name']
                    location.country_code = closest_city.get('country_code', 'NC')
                    logger.info(f"   ✅ Ville principale: {location.city}")
            except Exception as e:
                logger.warning(f"   ⚠️ Erreur recherche villes: {e}")
            
            # 4. IMPORTANT: Toujours essayer Nominatim si peu d'infos locales
            if location.confidence_score < 0.5 or not location.city:
                logger.info("   🌐 Fallback sur Nominatim (données locales insuffisantes)")
                nominatim_data = self._get_nominatim_data(latitude, longitude)
                if nominatim_data:
                    self._merge_nominatim_data(location, nominatim_data)
                    location.data_sources.append('nominatim')
                    location.confidence_score = max(location.confidence_score + 0.3, 0.5)
                    logger.info(f"   ✅ Nominatim: {location.formatted_address}")
            
            # 5. Rechercher POIs contextuels si toujours peu d'info
            if location.confidence_score < 0.7:
                try:
                    location.nearby_pois = self._search_nearby_pois(latitude, longitude, radius_km / 2)
                    if location.nearby_pois:
                        location.data_sources.append('overpass')
                        location.confidence_score += 0.2
                        logger.info(f"   ✅ {len(location.nearby_pois)} POIs trouvés")
                except Exception as e:
                    logger.warning(f"   ⚠️ Erreur recherche POIs: {e}")
            
            # 6. Finaliser les données
            self._finalize_location_data(location)
            
        except Exception as e:
            logger.error(f"❌ Erreur durant la géolocalisation: {e}")
            # En cas d'erreur totale, utiliser Nominatim directement
            try:
                logger.info("🌐 Tentative directe Nominatim après erreur DB")
                nominatim_data = self._get_nominatim_data(latitude, longitude)
                if nominatim_data:
                    self._merge_nominatim_data(location, nominatim_data)
                    location.data_sources = ['nominatim_fallback']
                    location.confidence_score = 0.3
            except:
                location.formatted_address = f"{latitude:.4f}, {longitude:.4f}"
                location.confidence_score = 0.1
        

        finally:
            self.disconnect_db()
        
        # Mettre en cache
        self._cache[cache_key] = (location, time.time())
        
        logger.info(f"🎯 Géolocalisation terminée (confiance: {location.confidence_score:.2f})")
        return location
    
    def _search_unesco_sites(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher les sites UNESCO dans le rayon spécifié"""
        query = """
            SELECT 
                id, name, latitude, longitude, country_code, category,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM unesco_sites 
            WHERE haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY distance_km ASC
            LIMIT 5
        """
        
        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        sites = self.cursor.fetchall()
        
        # Enrichir avec score de pertinence
        for site in sites:
            site['relevance_score'] = self._calculate_site_relevance(site, 'unesco')
            site['source'] = 'unesco'
        
        return sites
    
    def _search_cultural_sites(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher les sites culturels dans le rayon spécifié"""
        query = """
            SELECT 
                id, name, latitude, longitude, country_code, feature_code, site_type,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM cultural_sites 
            WHERE haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY distance_km ASC
            LIMIT 8
        """
        
        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        sites = self.cursor.fetchall()
        
        # Enrichir avec score de pertinence
        for site in sites:
            site['relevance_score'] = self._calculate_site_relevance(site, 'cultural')
            site['source'] = 'cultural'
        
        return sites
    
    def _search_major_cities(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher les villes importantes dans le rayon spécifié"""
        query = """
            SELECT 
                id, name, ascii_name, latitude, longitude, country_code, population,
                haversine_distance(%s, %s, latitude, longitude) as distance_km
            FROM geonames 
            WHERE feature_class = 'P' 
              AND feature_code IN ('PPL', 'PPLA', 'PPLA2', 'PPLA3', 'PPLC')
              AND population >= 1000
              AND haversine_distance(%s, %s, latitude, longitude) <= %s
            ORDER BY 
              CASE 
                WHEN feature_code = 'PPLC' THEN 1  -- Capitales en premier
                WHEN feature_code = 'PPLA' THEN 2  -- Puis centres admin
                ELSE 3 
              END,
              population DESC,
              distance_km ASC
            LIMIT 5
        """
        
        self.cursor.execute(query, (lat, lon, lat, lon, radius_km))
        cities = self.cursor.fetchall()
        
        # Enrichir avec métadonnées
        for city in cities:
            city['source'] = 'geonames'
            city['type'] = self._get_city_type(city.get('feature_code', 'PPL'))
        
        return cities
    
    def _calculate_site_relevance(self, site: Dict, site_type: str) -> float:
        """Calculer un score de pertinence pour un site"""
        relevance = 1.0
        distance_km = float(site.get('distance_km', 999))  # Convertir Decimal en float
        
        # Bonus selon le type de site
        if site_type == 'unesco':
            relevance += 0.8  # UNESCO = très pertinent
        elif site_type == 'cultural':
            feature_code = site.get('feature_code', '')
            if feature_code in ['HSTS', 'MUS', 'MNM']:
                relevance += 0.6
            elif feature_code in ['TMPL', 'PAL']:
                relevance += 0.5
            else:
                relevance += 0.3
        
        # Malus distance (plus c'est loin, moins c'est pertinent)
        if distance_km < 1:
            relevance += 0.3
        elif distance_km < 5:
            relevance += 0.1
        else:
            relevance -= distance_km * 0.05
        
        return max(0.1, relevance)
    
    def _get_city_type(self, feature_code: str) -> str:
        """Convertir le code GeoNames en type lisible"""
        city_types = {
            'PPLC': 'capitale',
            'PPLA': 'centre_administratif', 
            'PPLA2': 'chef_lieu_region',
            'PPLA3': 'chef_lieu_district',
            'PPL': 'ville'
        }
        return city_types.get(feature_code, 'localite')
    
    def _get_nominatim_data(self, lat: float, lon: float) -> Optional[Dict]:
        """Récupérer les données administratives via Nominatim"""
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
            
            response = requests.get(
                url,
                params=params,
                headers=self.nominatim_config['headers'],
                timeout=self.nominatim_config['timeout']
            )
            response.raise_for_status()
            
            data = response.json()
            return data if 'error' not in data else None
            
        except requests.RequestException as e:
            logger.warning(f"⚠️  Erreur Nominatim: {e}")
            return None
    
    def _search_nearby_pois(self, lat: float, lon: float, radius_km: float) -> List[Dict]:
        """Rechercher des POIs contextuels via Overpass API"""
        try:
            self._respect_rate_limit()
            
            radius_m = int(radius_km * 1000)
            query = f"""
            [out:json][timeout:10];
            (
              node["tourism"~"^(attraction|museum|monument|viewpoint)$"](around:{radius_m},{lat},{lon});
              node["historic"~"^(monument|archaeological_site|castle)$"](around:{radius_m},{lat},{lon});
              node["natural"~"^(peak|beach|bay|cape)$"](around:{radius_m},{lat},{lon});  
            );
            out body;
            """
            
            response = requests.post(
                self.overpass_config['base_url'],
                data={'data': query},
                timeout=self.overpass_config['timeout']
            )
            response.raise_for_status()
            
            data = response.json()
            elements = data.get('elements', [])
            
            # Traiter et scorer les POIs
            pois = []
            for element in elements[:self.overpass_config['max_pois']]:
                poi = self._process_overpass_poi(element, lat, lon)
                if poi:
                    pois.append(poi)
            
            # Trier par pertinence
            pois.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            return pois[:3]  # Top 3 seulement
            
        except requests.RequestException as e:
            logger.warning(f"⚠️  Erreur Overpass: {e}")
            return []
    
    def _process_overpass_poi(self, element: Dict, ref_lat: float, ref_lon: float) -> Optional[Dict]:
        """Traiter un POI d'Overpass et calculer sa pertinence"""
        tags = element.get('tags', {})
        poi_lat = element.get('lat', 0)
        poi_lon = element.get('lon', 0)
        
        # Nom du POI
        name = (tags.get('name:fr') or tags.get('name') or 
                tags.get('tourism') or tags.get('historic') or 
                tags.get('natural', 'POI'))
        
        if not name or name in ['yes', 'no']:
            return None
        
        # Calculer distance
        distance_m = self._haversine_distance(ref_lat, ref_lon, poi_lat, poi_lon) * 1000
        
        # Score de pertinence
        relevance = 1.0
        if tags.get('tourism') in ['attraction', 'museum', 'monument']:
            relevance += 0.5
        if tags.get('historic'):
            relevance += 0.4
        if tags.get('natural') in ['peak', 'beach', 'bay']:
            relevance += 0.3
        
        # Malus distance
        relevance -= distance_m / 5000  # -0.1 par 500m
        
        return {
            'name': name,
            'type': tags.get('tourism') or tags.get('historic') or tags.get('natural', 'poi'),
            'latitude': poi_lat,
            'longitude': poi_lon,
            'distance_m': int(distance_m),
            'relevance_score': max(0.1, relevance),
            'source': 'overpass',
            'tags': {k: v for k, v in tags.items() if k in ['cuisine', 'website', 'opening_hours']}
        }
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculer la distance haversine en km (version Python)"""
        from math import radians, cos, sin, asin, sqrt
        
        # Convertir en radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Formule haversine
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        
        return 6371 * c  # Rayon terre en km
    
    def _merge_nominatim_data(self, location: GeoLocation, nominatim_data: Dict):
        """Fusionner les données Nominatim dans la structure GeoLocation"""
        address = nominatim_data.get('address', {})
        
        # Adresse formatée
        location.formatted_address = nominatim_data.get('display_name', '')
        
        # Détails administratifs (si pas déjà remplis)
        if not location.city:
            location.city = (address.get('city') or address.get('town') or 
                           address.get('village') or address.get('municipality', ''))
        
        if not location.region:
            location.region = (address.get('state') or address.get('region') or 
                             address.get('province', ''))
        
        if not location.country:
            location.country = address.get('country', '')
        
        if not location.country_code:
            location.country_code = address.get('country_code', '').upper()
    
    def _finalize_location_data(self, location: GeoLocation):
        """Finaliser et optimiser les données de géolocalisation"""
        # Générer une adresse formatée intelligente
        if not location.formatted_address:
            if location.unesco_sites:
                # Prioriser UNESCO
                primary_site = location.unesco_sites[0]
                location.formatted_address = f"{primary_site['name']}"
                if location.city:
                    location.formatted_address += f", {location.city}"
                    
            elif location.cultural_sites:
                # Sinon site culturel principal
                primary_site = location.cultural_sites[0]
                location.formatted_address = f"{primary_site['name']}"
                if location.city:
                    location.formatted_address += f", {location.city}"
                    
            elif location.major_cities:
                # Sinon ville la plus proche
                closest_city = location.major_cities[0]
                location.formatted_address = f"{closest_city['name']}, {location.country}"
                
            else:
                # Fallback coordonnées
                location.formatted_address = f"{location.latitude:.4f}, {location.longitude:.4f}"
        
        # Nettoyer l'adresse si trop longue
        if len(location.formatted_address) > 100:
            if location.city and location.country:
                location.formatted_address = f"{location.city}, {location.country}"
            else:
                location.formatted_address = location.formatted_address[:97] + "..."
    
    def get_location_summary_for_ai(self, location: GeoLocation) -> Dict[str, str]:
        """
        Générer un résumé optimisé pour l'IA de génération de légendes
        
        Returns:
            Dict avec différents niveaux de contexte pour l'IA
        """
        summary = {
            'location_basic': f"{location.city}, {location.country}" if location.city else location.formatted_address,
            'location_detailed': location.formatted_address,
            'cultural_context': '',
            'nearby_attractions': '',
            'geographic_context': '',
            'confidence_level': 'high' if location.confidence_score > 0.7 else 'medium' if location.confidence_score > 0.4 else 'low'
        }
        
        # Contexte culturel/historique
        cultural_sites = []
        if location.unesco_sites:
            unesco_names = [site['name'] for site in location.unesco_sites[:2]]
            cultural_sites.extend([f"Site UNESCO: {name}" for name in unesco_names])
        
        if location.cultural_sites:
            cultural_names = [site['name'] for site in location.cultural_sites[:2]]
            cultural_sites.extend(cultural_names)
        
        if cultural_sites:
            summary['cultural_context'] = '; '.join(cultural_sites)
        
        # Attractions à proximité
        attractions = []
        if location.nearby_pois:
            poi_names = [poi['name'] for poi in location.nearby_pois 
                        if poi.get('relevance_score', 0) > 0.3]
            attractions.extend(poi_names)
        
        if attractions:
            summary['nearby_attractions'] = ', '.join(attractions[:3])
        
        # Contexte géographique
        geo_context = []
        if location.major_cities and len(location.major_cities) > 1:
            nearby_city = location.major_cities[1]  # Deuxième ville (première = actuelle)
            geo_context.append(f"Près de {nearby_city['name']}")
        
        if location.region:
            geo_context.append(location.region)
        
        if geo_context:
            summary['geographic_context'] = ', '.join(geo_context)
        
        return summary
    
    def search_by_name(self, search_term: str, country_code: str = None, 
                      limit: int = 10) -> List[Dict]:
        """
        Rechercher des lieux par nom (pour autocomplete/suggestions)
        
        Args:
            search_term: Terme de recherche
            country_code: Code pays optionnel (ex: 'FR', 'ID')
            limit: Nombre max de résultats
            
        Returns:
            Liste des lieux correspondants avec coordonnées
        """
        try:
            self.connect_db()
            
            # Préparer la requête avec ou sans filtre pays
            where_country = "AND country_code = %s" if country_code else ""
            params = [f"%{search_term}%", f"%{search_term}%"]
            if country_code:
                params.append(country_code.upper())
            params.append(limit)
            
            query = f"""
                (
                    SELECT 'unesco' as source, id, name, latitude, longitude, country_code, 
                           'UNESCO' as type, 0 as population
                    FROM unesco_sites 
                    WHERE (name LIKE %s OR ascii_name LIKE %s) {where_country}
                )
                UNION ALL
                (
                    SELECT 'geonames' as source, id, name, latitude, longitude, country_code,
                           feature_code as type, population
                    FROM geonames 
                    WHERE (name LIKE %s OR ascii_name LIKE %s) 
                      AND feature_class IN ('P', 'S') {where_country}
                    ORDER BY population DESC
                )
                ORDER BY 
                    CASE source WHEN 'unesco' THEN 1 ELSE 2 END,
                    population DESC
                LIMIT %s
            """
            
            # Doubler les paramètres pour la deuxième partie de l'UNION
            if country_code:
                query_params = params[:3] + params[:3] + [params[3]]  # search x2 + country + limit
            else:
                query_params = params[:2] + params[:2] + [params[2]]  # search x2 + limit
            
            self.cursor.execute(query, query_params)
            results = self.cursor.fetchall()
            
            return results
            
        except mysql.connector.Error as e:
            logger.error(f"❌ Erreur recherche par nom: {e}")
            return []
        finally:
            self.disconnect_db()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Retourner les statistiques du cache"""
        valid_entries = 0
        total_entries = len(self._cache)
        
        current_time = time.time()
        for _, (_, timestamp) in self._cache.items():
            if self._is_cache_valid(timestamp):
                valid_entries += 1
        
        return {
            'total_entries': total_entries,
            'valid_entries': valid_entries,
            'expired_entries': total_entries - valid_entries,
            'cache_ttl_seconds': self.cache_ttl,
            'hit_rate': f"{(valid_entries/total_entries*100):.1f}%" if total_entries > 0 else "0%"
        }
    
    def clear_cache(self):
        """Vider le cache"""
        self._cache.clear()
        logger.info("🗑️  Cache vidé")


# Exemple d'utilisation et tests
if __name__ == "__main__":
    # Configuration de test
    db_config = {
        'host': 'localhost',
        'user': 'root', 
        'password': 'mysqlroot',
        'database': 'immich_gallery',
        'charset': 'utf8mb4'
    }
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialiser le service
    geo_service = GeoService(db_config)
    
    # === COORDONNÉES DE TEST ===
    test_locations = [
        # Angkor Wat, Cambodge (UNESCO)
        (13.4125, 103.8667, "Angkor Wat - Site UNESCO majeur"),
        
        # Nouméa, Nouvelle-Calédonie  
        (-22.2697, 166.4381, "Nouméa - Centre urbain Pacifique"),
        
        # Bali, Indonésie (nombreux sites culturels)
        (-8.4095, 115.1889, "Ubud, Bali - Centre culturel"),
        
        # Paris, France (test ville européenne)
        (48.8566, 2.3522, "Paris - Capitale européenne"),
        
        # Bangkok, Thaïlande (mégapole asiatique)
        (13.7563, 100.5018, "Bangkok - Mégapole thaïlandaise")
    ]
    
    logger.info("🧪 Tests du GeoService")
    logger.info("=" * 50)
    
    for lat, lon, description in test_locations:
        print(f"\n🌍 Test: {description}")
        print(f"📍 Coordonnées: {lat}, {lon}")
        
        try:
            # Géolocalisation complète
            location = geo_service.get_location_info(lat, lon, radius_km=15)
            
            print(f"📍 Adresse: {location.formatted_address}")
            print(f"🎯 Confiance: {location.confidence_score:.2f}")
            print(f"📊 Sources: {', '.join(location.data_sources)}")
            
            if location.unesco_sites:
                print(f"🏛️  UNESCO: {len(location.unesco_sites)} sites")
                for site in location.unesco_sites[:2]:
                    print(f"   - {site['name']} ({site['distance_km']:.1f}km)")
            
            if location.cultural_sites:
                print(f"🎭 Culturel: {len(location.cultural_sites)} sites")
                for site in location.cultural_sites[:2]:
                    print(f"   - {site['name']} ({site['distance_km']:.1f}km)")
            
            if location.major_cities:
                print(f"🏙️  Villes: {len(location.major_cities)} proches")
                for city in location.major_cities[:2]:
                    print(f"   - {city['name']} ({city['distance_km']:.1f}km, {city['population']:,} hab)")
            
            # Résumé pour IA
            ai_summary = geo_service.get_location_summary_for_ai(location)
            print(f"\n🤖 Résumé IA:")
            for key, value in ai_summary.items():
                if value:
                    print(f"   {key}: {value}")
                    
        except Exception as e:
            print(f"❌ Erreur: {e}")
    
    # Test recherche par nom
    print(f"\n🔍 Test recherche par nom:")
    results = geo_service.search_by_name("Bali", limit=5)
    for result in results:
        print(f"   - {result['name']} ({result['source']}) - {result['country_code']}")
    
    # Stats du cache
    cache_stats = geo_service.get_cache_stats()
    print(f"\n📊 Stats cache: {cache_stats}")
    
    print(f"\n🎉 Tests terminés !")