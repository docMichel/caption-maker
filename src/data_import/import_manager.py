# src/data_import/import_manager.py
import logging
from typing import Optional, Set
from .country_detector import CountryDetector
#from .importers import GeoNamesImporter, UNESCOImporter, OSMImporter

logger = logging.getLogger(__name__)

class ImportManager:
    def __init__(self, db_config: dict):
        self.db_config = db_config
        self.country_detector = CountryDetector()
        try:
            from .importers.geonames_importer import GeoNamesImporter
            from .importers.unesco_importer import UNESCOImporter
            # from .importers.osm_importer import OSMImporter  # Si pas encore créé
            
            self.importers = {
                'geonames': GeoNamesImporter(db_config),
                'unesco': UNESCOImporter(db_config),
                # 'osm': OSMImporter(db_config)
            }
        except ImportError as e:
            logger.warning(f"Importers non disponibles: {e}")
            self.importers = {}
        


    def ensure_data_for_location(self, lat: float, lon: float) -> str:
        """S'assurer que les données sont disponibles pour cette localisation"""
        logger.info(f"📍 ensure_data_for_location({lat}, {lon})")

        # 1. Détecter le pays
        country_code = self.country_detector.detect_country(lat, lon)
        if not country_code:
            logger.warning(f"Impossible de détecter le pays pour {lat}, {lon}")
            return "NC"
        
        # 2. Vérifier si déjà importé
        is_imported = self._is_country_imported(country_code)
        logger.info(f"   Déjà importé? {is_imported}")
        
        if not is_imported:
            logger.info(f"   🌍 Lancement import des données pour {country_code}")
            self._import_country_data(country_code)
        else:
            logger.info(f"   ✅ Données déjà importées pour {country_code}")
            
        return country_code
    
    def _is_country_imported(self, country_code: str) -> bool:
        """Vérifier si un pays est déjà importé"""
        import mysql.connector
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT COUNT(*) FROM country_imports WHERE country_code = %s",
            (country_code,)
        )
        result = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        return result > 0
    
    def _import_country_data(self, country_code: str):
        """Importer toutes les données pour un pays"""
        logger.info(f"🌍 Import des données pour {country_code}")
        logger.info(f"   Importers disponibles: {list(self.importers.keys())}")
        
        stats = {}
        
        # 1. GeoNames
        if 'geonames' in self.importers:
            try:
                logger.info(f"   Lancement import GeoNames...")
                stats['cities'] = self.importers['geonames'].import_country(country_code)
                logger.info(f"   ✅ {stats['cities']} lieux importés depuis GeoNames")
            except Exception as e:
                logger.error(f"   ❌ Erreur import GeoNames: {e}")
                import traceback
                traceback.print_exc()
                stats['cities'] = 0
        else:
            logger.warning("   ⚠️ GeoNamesImporter non disponible")
        
        # 2. UNESCO
        if 'unesco' in self.importers:
            try:
                logger.info(f"   Lancement import UNESCO...")
                stats['unesco'] = self.importers['unesco'].import_country(country_code)
                logger.info(f"   ✅ {stats['unesco']} sites UNESCO importés")
            except Exception as e:
                logger.error(f"   ❌ Erreur import UNESCO: {e}")
                stats['unesco'] = 0
        else:
            logger.warning("   ⚠️ UNESCOImporter non disponible")
        
        # 3. Enregistrer l'import
        logger.info(f"   Enregistrement import: {stats}")
        self._record_import(country_code, stats)
    def X_import_country_data(self, country_code: str):
        """Importer toutes les données pour un pays"""
        stats = {}
        
        # 1. GeoNames
        try:
            stats['cities'] = self.importers['geonames'].import_country(country_code)
            logger.info(f"✅ {stats['cities']} lieux importés depuis GeoNames")
        except Exception as e:
            logger.error(f"❌ Erreur import GeoNames: {e}")
            stats['cities'] = 0
        
        # 2. UNESCO
        try:
            stats['unesco'] = self.importers['unesco'].import_country(country_code)
            logger.info(f"✅ {stats['unesco']} sites UNESCO importés")
        except Exception as e:
            logger.error(f"❌ Erreur import UNESCO: {e}")
            stats['unesco'] = 0
        
        # 3. Enregistrer l'import
        self._record_import(country_code, stats)
    
    def _record_import(self, country_code: str, stats: dict):
        """Enregistrer qu'un pays a été importé"""
        import mysql.connector
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO country_imports 
            (country_code, cities_count, unesco_count) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
            cities_count = VALUES(cities_count),
            unesco_count = VALUES(unesco_count),
            last_updated = CURRENT_DATE
        """, (country_code, stats.get('cities', 0), stats.get('unesco', 0)))
        
        conn.commit()
        cursor.close()
        conn.close()        
        logger.info("ImportManager créé")
