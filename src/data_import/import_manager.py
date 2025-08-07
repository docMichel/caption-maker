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
            from .importers.cultural_importer  import CulturalImporter

            from .importers.osm_importer import OSMImporter  # Si pas encore créé
            
            self.importers = {
                'geonames': GeoNamesImporter(db_config),
                'unesco': UNESCOImporter(db_config),
                'cultural': CulturalImporter(db_config),
                'osm': OSMImporter(db_config)
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
        
        try:
            # D'abord vérifier si la table existe
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = %s 
                AND table_name = 'country_imports'
            """, (self.db_config['database'],))
            
            if cursor.fetchone()[0] == 0:
                logger.info("   Table country_imports n'existe pas")
                return False
            
            # Ensuite vérifier si le pays est importé
            cursor.execute(
                "SELECT COUNT(*) FROM country_imports WHERE country_code = %s",
                (country_code,)
            )
            result = cursor.fetchone()[0]
            
            logger.info(f"   country_imports check: {result} entrées pour {country_code}")
            return result > 0
            
        except Exception as e:
            logger.error(f"   Erreur vérification import: {e}")
            return False
        finally:
            cursor.close()
            conn.close()

    
    
    
    
    def _import_country_data(self, country_code: str):
        """Importer toutes les données pour un pays"""
        logger.info(f"🌍 Import des données pour {country_code}")
        logger.info(f"   Importers disponibles: {list(self.importers.keys())}")
        
        stats = {}
        success = False
        
        # Liste des importers dans l'ordre
        import_order = ['geonames', 'cultural', 'unesco', 'osm']
        
        for importer_name in import_order:
            if importer_name in self.importers:
                try:
                    logger.info(f"   📥 Lancement import {importer_name}...")
                    count = self.importers[importer_name].import_country(country_code)
                    stats[importer_name] = count
                    
                    if count > 0:
                        success = True
                        logger.info(f"   ✅ {count} entrées importées depuis {importer_name}")
                    else:
                        logger.warning(f"   ⚠️ Aucune donnée importée depuis {importer_name}")
                        
                except Exception as e:
                    logger.error(f"   ❌ Erreur import {importer_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    stats[importer_name] = 0
            else:
                logger.warning(f"   ⚠️ Importer {importer_name} non disponible")
    
    def X_import_country_data(self, country_code: str):
        """Importer toutes les données pour un pays"""
        logger.info(f"🌍 Import des données pour {country_code}")
        logger.info(f"   Importers disponibles: {list(self.importers.keys())}")
        
        stats = {}
        success = False  # Flag pour savoir si au moins un import a réussi
        
        # 1. GeoNames
        if 'geonames' in self.importers:
            try:
                logger.info(f"   Lancement import GeoNames...")
                count = self.importers['geonames'].import_country(country_code)
                stats['cities'] = count
                if count > 0:
                    success = True
                    logger.info(f"   ✅ {count} lieux importés depuis GeoNames")
                else:
                    logger.warning(f"   ⚠️ Aucune donnée GeoNames importée")
            except Exception as e:
                logger.error(f"   ❌ Erreur import GeoNames: {e}")
                import traceback
                traceback.print_exc()
                stats['cities'] = 0
                
        # 3. Sites culturels (après GeoNames)
        if 'cultural' in self.importers and 'geonames' in self.importers:
            try:
                logger.info(f"   Lancement import sites culturels...")
                count = self.importers['cultural'].import_country(country_code)
                stats['cultural'] = count
                if count > 0:
                    success = True
                    logger.info(f"   ✅ {count} sites culturels importés")
            except Exception as e:
                logger.error(f"   ❌ Erreur import culturel: {e}")
                stats['cultural'] = 0

        # 2. UNESCO (même logique)
        if 'unesco' in self.importers:
            try:
                count = self.importers['unesco'].import_country(country_code)
                stats['unesco'] = count
                if count > 0:
                    success = True
            except Exception as e:
                logger.error(f"   ❌ Erreur import UNESCO: {e}")
                stats['unesco'] = 0
        
        # 3. Enregistrer SEULEMENT si au moins un import a réussi
        if success:
            logger.info(f"   Enregistrement import: {stats}")
            self._record_import(country_code, stats)
        else:
            logger.error(f"   ❌ Aucun import réussi pour {country_code}, pas d'enregistrement")


    def _record_import(self, country_code: str, stats: dict):
        """Enregistrer qu'un pays a été importé"""
        # Ne pas enregistrer si rien n'a été importé
        total_imported = stats.get('cities', 0) + stats.get('unesco', 0)
        if total_imported == 0:
            logger.warning(f"   ⚠️ Aucune donnée importée pour {country_code}, pas d'enregistrement")
            return
            
        import mysql.connector
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
      
            cursor.execute("""
                INSERT INTO country_imports 
                (country_code, cities_count, unesco_count, cultural_count, osm_count) 
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                cities_count = VALUES(cities_count),
                unesco_count = VALUES(unesco_count),
                cultural_count = VALUES(cultural_count),
                osm_count = VALUES(osm_count),
                last_updated = CURRENT_DATE
            """, (country_code, 
                stats.get('cities', 0), 
                stats.get('unesco', 0),
                stats.get('cultural', 0),
                stats.get('osm', 0)))

            conn.commit()
            logger.info(f"   ✅ Import enregistré pour {country_code}: {total_imported} entrées")
            
        finally:
            cursor.close()
            conn.close()
