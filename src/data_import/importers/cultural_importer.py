# src/data_import/importers/cultural_importer.py
import logging
import mysql.connector

logger = logging.getLogger(__name__)

class CulturalImporter:
    def __init__(self, db_config):
        self.db_config = db_config
        
    def import_country(self, country_code: str) -> int:
        """
        Importer les sites culturels depuis GeoNames
        (filtrer les codes feature culturels)
        """
        logger.info(f"📥 Import sites culturels pour {country_code}")
        
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # Extraire les sites culturels depuis geonames
            query = """
                INSERT INTO cultural_sites 
                (name, latitude, longitude, country_code, feature_code, site_type)
                SELECT 
                    name, 
                    latitude, 
                    longitude, 
                    country_code,
                    feature_code,
                    CASE 
                        WHEN feature_code = 'MUS' THEN 'museum'
                        WHEN feature_code = 'MNMT' THEN 'monument'
                        WHEN feature_code = 'HSTS' THEN 'historic_site'
                        WHEN feature_code = 'RUIN' THEN 'ruins'
                        WHEN feature_code = 'CSTL' THEN 'castle'
                        WHEN feature_code = 'PAL' THEN 'palace'
                        WHEN feature_code = 'CH' THEN 'church'
                        WHEN feature_code = 'MSQE' THEN 'mosque'
                        WHEN feature_code = 'TMPL' THEN 'temple'
                        WHEN feature_code = 'SHRN' THEN 'shrine'
                        WHEN feature_code = 'ARCH' THEN 'arch'
                        WHEN feature_code = 'AMTH' THEN 'amphitheatre'
                        WHEN feature_code = 'THTR' THEN 'theatre'
                        WHEN feature_code = 'GDN' THEN 'garden'
                        WHEN feature_code = 'LIBR' THEN 'library'
                        WHEN feature_code = 'OPRA' THEN 'opera_house'
                        ELSE 'cultural_site'
                    END as site_type
                FROM geonames 
                WHERE country_code = %s
                AND feature_code IN (
                    'MUS', 'MNMT', 'HSTS', 'RUIN', 'CSTL', 'PAL',
                    'CH', 'MSQE', 'TMPL', 'SHRN', 'ARCH', 'AMTH',
                    'THTR', 'GDN', 'LIBR', 'OPRA', 'TOWR', 'WALL',
                    'BLDG', 'CTRS', 'SCHC', 'UNIV'
                )
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    site_type = VALUES(site_type)
            """
            
            cursor.execute(query, (country_code,))
            count = cursor.rowcount
            conn.commit()
            
            logger.info(f"✅ {count} sites culturels importés")
            return count
            
        except Exception as e:
            logger.error(f"❌ Erreur import sites culturels: {e}")
            conn.rollback()
            return 0
        finally:
            cursor.close()
            conn.close()