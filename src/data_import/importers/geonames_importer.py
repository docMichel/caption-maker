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
                        if len(row) >= 15:  # S'assurer qu'on a assez de colonnes
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
                                'admin1_code': row[10],
                                'admin2_code': row[11],
                                'population': int(row[14]) if row[14] else 0,
                                'elevation': int(row[15]) if row[15] else None,
                                'timezone': row[17] if len(row) > 17 else None
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
            # Créer la table si elle n'existe pas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS geonames (
                    id INT PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    ascii_name VARCHAR(200) NOT NULL,
                    latitude DECIMAL(10, 7) NOT NULL,
                    longitude DECIMAL(10, 7) NOT NULL,
                    feature_class CHAR(1) NOT NULL,
                    feature_code VARCHAR(10) NOT NULL,
                    country_code CHAR(2) NOT NULL,
                    admin1_code VARCHAR(20),
                    admin2_code VARCHAR(20),
                    population INT DEFAULT 0,
                    elevation INT DEFAULT NULL,
                    timezone VARCHAR(40),
                    INDEX idx_coords (latitude, longitude),
                    INDEX idx_country (country_code),
                    INDEX idx_feature (feature_class, feature_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            # Préparer l'insertion
            insert_query = """
                INSERT INTO geonames 
                (id, name, ascii_name, latitude, longitude, feature_class, 
                 feature_code, country_code, admin1_code, admin2_code, 
                 population, elevation, timezone)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    population = VALUES(population)
            """
            
            # Insérer par batch
            batch_size = 1000
            total_inserted = 0
            
            for i in range(0, len(data), batch_size):
                batch = data[i:i + batch_size]
                values = [
                    (d['geonameid'], d['name'], d['asciiname'], 
                     d['latitude'], d['longitude'], d['feature_class'],
                     d['feature_code'], d['country_code'], d['admin1_code'],
                     d['admin2_code'], d['population'], d['elevation'], 
                     d['timezone'])
                    for d in batch
                ]
                
                cursor.executemany(insert_query, values)
                total_inserted += cursor.rowcount
                
                if (i + batch_size) % 10000 == 0:
                    logger.info(f"   Progression: {i + batch_size}/{len(data)}")
                    conn.commit()
            
            conn.commit()
            return total_inserted
            
        finally:
            cursor.close()
            conn.close()