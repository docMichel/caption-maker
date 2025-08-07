# src/data_import/importers/geonames_importer.py
import logging
import requests
import zipfile
import io
import csv
import mysql.connector
from typing import List, Dict

logger = logging.getLogger(__name__)

class GeoNamesImporter:
    def __init__(self, db_config):
        self.db_config = db_config
        self.base_url = "http://download.geonames.org/export/dump/"
        
    def import_country(self, country_code: str) -> int:
        """Importer les données GeoNames pour un pays"""
        logger.info(f"📥 Import GeoNames pour {country_code}")
        
        try:
            # 1. Télécharger le fichier
            data = self._download_country_file(country_code)
            if not data:
                return 0
            
            # 2. Parser et insérer dans la base
            count = self._import_to_database(data, country_code)
            
            logger.info(f"✅ {count} entrées importées pour {country_code}")
            return count
            
        except Exception as e:
            logger.error(f"❌ Erreur import GeoNames {country_code}: {e}")
            return 0
    
    def _download_country_file(self, country_code: str) -> List[Dict]:
        """Télécharger et parser le fichier GeoNames"""
        file_url = f"{self.base_url}{country_code}.zip"
        logger.info(f"   Téléchargement: {file_url}")
        
        try:
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()
            
            # Décompresser le ZIP en mémoire
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                # Le fichier principal est {country_code}.txt
                filename = f"{country_code}.txt"
                
                with zf.open(filename) as f:
                    # Parser le TSV
                    reader = csv.reader(io.TextIOWrapper(f, 'utf-8'), delimiter='\t')
                    
                    data = []
                    for row in reader:
                        if len(row) >= 19:  # S'assurer qu'on a toutes les colonnes
                            data.append({
                                'geonameid': int(row[0]),
                                'name': row[1],
                                'asciiname': row[2],
                                'alternatenames': row[3],
                                'latitude': float(row[4]),
                                'longitude': float(row[5]),
                                'feature_class': row[6],
                                'feature_code': row[7],
                                'country_code': row[8],
                                'cc2': row[9],
                                'admin1_code': row[10],
                                'admin2_code': row[11],
                                'admin3_code': row[12],
                                'admin4_code': row[13],
                                'population': int(row[14]) if row[14] else 0,
                                'elevation': int(row[15]) if row[15] and row[15].strip() else None,
                                'dem': int(row[16]) if row[16] and row[16].strip() else None,
                                'timezone': row[17] if len(row) > 17 else None,
                                'modification_date': row[18] if len(row) > 18 else None
                            })
                    
                    logger.info(f"   {len(data)} entrées lues")
                    return data
                    
        except requests.RequestException as e:
            logger.error(f"   Erreur téléchargement: {e}")
            return []
    
    def _import_to_database(self, data: List[Dict], country_code: str) -> int:
        """Insérer les données dans MySQL"""
        if not data:
            return 0
            
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # Créer la table si elle n'existe pas avec TOUS les champs corrects
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS geonames (
                    geonameid INT PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    asciiname VARCHAR(200),
                    alternatenames TEXT,
                    latitude DECIMAL(10, 7) NOT NULL,
                    longitude DECIMAL(10, 7) NOT NULL,
                    feature_class CHAR(1),
                    feature_code VARCHAR(10),
                    country_code CHAR(2),
                    cc2 VARCHAR(200),
                    admin1_code VARCHAR(20),
                    admin2_code VARCHAR(80),
                    admin3_code VARCHAR(20),
                    admin4_code VARCHAR(20),
                    population BIGINT DEFAULT 0,
                    elevation INT,
                    dem INT,
                    timezone VARCHAR(40),
                    modification_date DATE,
                    
                    INDEX idx_coords (latitude, longitude),
                    INDEX idx_country (country_code),
                    INDEX idx_feature (feature_class, feature_code),
                    INDEX idx_population (population DESC),
                    INDEX idx_name (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            # Préparer l'insertion avec TOUS les champs
            insert_query = """
                INSERT INTO geonames 
                (geonameid, name, asciiname, alternatenames, latitude, longitude, 
                 feature_class, feature_code, country_code, cc2, admin1_code, 
                 admin2_code, admin3_code, admin4_code, population, elevation, 
                 dem, timezone, modification_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    population = VALUES(population),
                    modification_date = VALUES(modification_date)
            """
            
            # Insérer par batch
            batch_size = 1000
            total_inserted = 0
            
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                values = []
                
                for d in batch:
                    # Gérer la date de modification
                    mod_date = None
                    if d.get('modification_date'):
                        try:
                            mod_date = d['modification_date']
                        except:
                            mod_date = None
                    
                    values.append((
                        d['geonameid'], 
                        d['name'], 
                        d['asciiname'],
                        d['alternatenames'][:65535] if d['alternatenames'] else None,  # Limiter TEXT
                        d['latitude'], 
                        d['longitude'], 
                        d['feature_class'],
                        d['feature_code'], 
                        d['country_code'], 
                        d['cc2'],
                        d['admin1_code'],
                        d['admin2_code'], 
                        d['admin3_code'],
                        d['admin4_code'],
                        d['population'], 
                        d['elevation'],
                        d['dem'],
                        d['timezone'],
                        mod_date
                    ))
                
                cursor.executemany(insert_query, values)
                total_inserted += cursor.rowcount
                
                if (i + batch_size) % 1000 == 0:
                    logger.info(f"   Progression: {i + batch_size}/{len(data)}")
                    conn.commit()
            
            conn.commit()
            logger.info(f"   ✅ Import terminé: {total_inserted} entrées")
            return len(data)  # Retourner le nombre total d'entrées traitées
            
        except Exception as e:
            logger.error(f"   ❌ Erreur DB: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()