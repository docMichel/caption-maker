#!/usr/bin/env python3
"""
Import des données géographiques dans MySQL
Script principal pour nettoyer et importer les fichiers GeoNames
"""

import os
import sys
import csv
import mysql.connector
from pathlib import Path
import argparse
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging
from tqdm import tqdm

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('import_geonames.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GeoDataImporter:
    """Importeur de données géographiques dans MySQL"""
    
    def __init__(self, data_path: str, db_config: Dict[str, str]):
        """
        Initialiser l'importeur
        
        Args:
            data_path: Chemin vers les fichiers de données
            db_config: Configuration de la base de données
        """
        self.data_path = Path(data_path).expanduser()
        self.db_config = db_config
        self.connection = None
        self.cursor = None
        
        # Statistiques d'import
        self.stats = {
            'geonames': {'imported': 0, 'skipped': 0},
            'unesco': {'imported': 0, 'skipped': 0},
            'cultural': {'imported': 0, 'skipped': 0},
            'postal': {'imported': 0, 'skipped': 0}
        }
        
        # Configuration des fichiers à traiter
        self.file_config = {
            'unesco': {
                'filename': 'unesco_heritage.txt',
                'exclude_features': ['HTL'],  # Exclure les hôtels
                'required_features': ['HSTS', 'MUS', 'MNM', 'TMPL', 'PAL']
            },
            'cultural': {
                'filename': 'cultural_sites_clean.txt',
                'exclude_features': ['HTL'],
                'required_features': ['HSTS', 'MUS', 'MNM', 'TMPL', 'PAL', 'ARCH']
            }
        }
    
    def connect_db(self):
        """Connexion à la base de données"""
        try:
            self.connection = mysql.connector.connect(**self.db_config)
            self.cursor = self.connection.cursor()
            logger.info("✅ Connexion MySQL établie")
        except mysql.connector.Error as e:
            logger.error(f"❌ Erreur connexion MySQL: {e}")
            sys.exit(1)
    
    def disconnect_db(self):
        """Fermer la connexion"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
        logger.info("🔌 Connexion MySQL fermée")
    
    def parse_geonames_line(self, line: str, source_file: str = "") -> Optional[Dict]:
        """
        Parser une ligne au format GeoNames
        
        Format: ID|Name|ASCII|Alt_names|Lat|Lon|Class|Code|Country|Admin1|Admin2|Pop|Elev|TZ|Modified
        """
        try:
            parts = line.strip().split('\t')
            if len(parts) < 14:
                return None
            
            # Nettoyer et valider les coordonnées
            try:
                lat = float(parts[4])
                lon = float(parts[5])
                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    return None
            except (ValueError, IndexError):
                return None
            
            # Nettoyer la population
            try:
                population = int(parts[11]) if parts[11] and parts[11] != '0' else 0
            except (ValueError, IndexError):
                population = 0
            
            # Nettoyer l'élévation
            try:
                elevation = int(parts[12]) if parts[12] and parts[12] not in ['', '0', '-9999'] else None
            except (ValueError, IndexError):
                elevation = None
            
            # Nettoyer la date
            try:
                mod_date = datetime.strptime(parts[14], '%Y-%m-%d').date() if len(parts) > 14 and parts[14] else None
            except (ValueError, IndexError):
                mod_date = None
            
            return {
                'id': int(parts[0]),
                'name': parts[1][:200],  # Limiter la longueur
                'ascii_name': parts[2][:200],
                'alternate_names': parts[3][:1000] if parts[3] else None,
                'latitude': lat,
                'longitude': lon,
                'feature_class': parts[6][:1],
                'feature_code': parts[7][:10],
                'country_code': parts[8][:2],
                'admin1_code': parts[9][:20] if parts[9] else None,
                'admin2_code': parts[10][:20] if parts[10] else None,
                'population': population,
                'elevation': elevation,
                'timezone': parts[13][:40] if len(parts) > 13 and parts[13] else None,
                'modification_date': mod_date
            }
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Erreur parsing ligne de {source_file}: {e}")
            return None
    
    def parse_postal_line(self, line: str) -> Optional[Dict]:
        """
        Parser une ligne de code postal
        
        Format: Country|Postal|Place|Admin1Name|Admin1Code|Admin2Name|Admin2Code|Admin3Name|Admin3Code|Lat|Lon|Accuracy
        """
        try:
            parts = line.strip().split('\t')
            if len(parts) < 11:
                return None
            
            # Valider coordonnées
            try:
                lat = float(parts[9])
                lon = float(parts[10])
                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    return None
            except (ValueError, IndexError):
                return None
            
            return {
                'country_code': parts[0][:2],
                'postal_code': parts[1][:20],
                'place_name': parts[2][:180],
                'admin1_name': parts[3][:100] if parts[3] else None,
                'admin1_code': parts[4][:20] if parts[4] else None,
                'admin2_name': parts[5][:100] if parts[5] else None,
                'admin2_code': parts[6][:20] if parts[6] else None,
                'admin3_name': parts[7][:100] if parts[7] else None,
                'admin3_code': parts[8][:20] if parts[8] else None,
                'latitude': lat,
                'longitude': lon,
                'accuracy': int(parts[11]) if len(parts) > 11 and parts[11] else 1
            }
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Erreur parsing ligne postal: {e}")
            return None
    
    def import_geonames_file(self, filepath: Path, table_name: str = 'geonames', 
                           chunk_size: int = 1000) -> Tuple[int, int]:
        """
        Importer un fichier GeoNames dans la table spécifiée
        
        Returns:
            Tuple (imported_count, skipped_count)
        """
        if not filepath.exists():
            logger.warning(f"⚠️  Fichier non trouvé: {filepath}")
            return 0, 0
        
        logger.info(f"📥 Import de {filepath.name} vers {table_name}")
        
        # Préparer la requête d'insertion selon la table
        if table_name == 'geonames':
            insert_query = """
                INSERT IGNORE INTO geonames 
                (id, name, ascii_name, alternate_names, latitude, longitude, 
                 feature_class, feature_code, country_code, admin1_code, admin2_code, 
                 population, elevation, timezone, modification_date)
                VALUES (%(id)s, %(name)s, %(ascii_name)s, %(alternate_names)s, 
                        %(latitude)s, %(longitude)s, %(feature_class)s, %(feature_code)s, 
                        %(country_code)s, %(admin1_code)s, %(admin2_code)s, 
                        %(population)s, %(elevation)s, %(timezone)s, %(modification_date)s)
            """
        elif table_name == 'unesco_sites':
            insert_query = """
                INSERT IGNORE INTO unesco_sites 
                (id, name, ascii_name, alternate_names, latitude, longitude, 
                 country_code, admin1_code, category, elevation, timezone, modification_date)
                VALUES (%(id)s, %(name)s, %(ascii_name)s, %(alternate_names)s, 
                        %(latitude)s, %(longitude)s, %(country_code)s, %(admin1_code)s, 
                        'heritage', %(elevation)s, %(timezone)s, %(modification_date)s)
            """
        elif table_name == 'cultural_sites':
            insert_query = """
                INSERT IGNORE INTO cultural_sites 
                (id, name, ascii_name, alternate_names, latitude, longitude, 
                 feature_class, feature_code, country_code, admin1_code, admin2_code,
                 site_type, elevation, timezone, modification_date)
                VALUES (%(id)s, %(name)s, %(ascii_name)s, %(alternate_names)s, 
                        %(latitude)s, %(longitude)s, %(feature_class)s, %(feature_code)s,
                        %(country_code)s, %(admin1_code)s, %(admin2_code)s,
                        %(feature_code)s, %(elevation)s, %(timezone)s, %(modification_date)s)
            """
        
        imported = 0
        skipped = 0
        batch_data = []
        
        # Compter les lignes pour la barre de progression
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            total_lines = sum(1 for _ in f)
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            pbar = tqdm(total=total_lines, desc=f"Import {filepath.name}")
            
            for line_num, line in enumerate(f, 1):
                pbar.update(1)
                
                if not line.strip():
                    continue
                
                # Parser la ligne
                data = self.parse_geonames_line(line, filepath.name)
                if not data:
                    skipped += 1
                    continue
                
                # Filtres spécifiques selon le type
                if table_name == 'unesco_sites':
                    # Exclure les hôtels et autres POI non-culturels
                    if (data['feature_code'] in self.file_config['unesco']['exclude_features'] or
                        data['feature_class'] != 'S'):
                        skipped += 1
                        continue
                
                elif table_name == 'cultural_sites':
                    # Ne garder que les sites culturels authentiques
                    if (data['feature_code'] in self.file_config['cultural']['exclude_features'] or
                        data['feature_class'] != 'S'):
                        skipped += 1
                        continue
                
                batch_data.append(data)
                
                # Insérer par chunks
                if len(batch_data) >= chunk_size:
                    try:
                        self.cursor.executemany(insert_query, batch_data)
                        self.connection.commit()
                        imported += len(batch_data)
                        batch_data = []
                    except mysql.connector.Error as e:
                        logger.error(f"Erreur insertion ligne {line_num}: {e}")
                        skipped += len(batch_data)
                        batch_data = []
            
            # Insérer le dernier batch
            if batch_data:
                try:
                    self.cursor.executemany(insert_query, batch_data)
                    self.connection.commit()
                    imported += len(batch_data)
                except mysql.connector.Error as e:
                    logger.error(f"Erreur insertion final batch: {e}")
                    skipped += len(batch_data)
            
            pbar.close()
        
        logger.info(f"✅ {filepath.name}: {imported} importés, {skipped} ignorés")
        return imported, skipped
    
    def import_postal_codes(self, chunk_size: int = 1000) -> Tuple[int, int]:
        """Importer tous les fichiers de codes postaux"""
        logger.info("📮 Import des codes postaux")
        
        insert_query = """
            INSERT IGNORE INTO postal_codes 
            (country_code, postal_code, place_name, admin1_name, admin1_code,
             admin2_name, admin2_code, admin3_name, admin3_code, 
             latitude, longitude, accuracy)
            VALUES (%(country_code)s, %(postal_code)s, %(place_name)s, 
                    %(admin1_name)s, %(admin1_code)s, %(admin2_name)s, %(admin2_code)s,
                    %(admin3_name)s, %(admin3_code)s, %(latitude)s, %(longitude)s, %(accuracy)s)
        """
        
        total_imported = 0
        total_skipped = 0
        
        # Chercher tous les fichiers *_postal.txt
        postal_files = list(self.data_path.glob("*_postal.txt"))
        
        for postal_file in postal_files:
            logger.info(f"📥 Import {postal_file.name}")
            
            imported = 0
            skipped = 0
            batch_data = []
            
            with open(postal_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    data = self.parse_postal_line(line)
                    if not data:
                        skipped += 1
                        continue
                    
                    batch_data.append(data)
                    
                    if len(batch_data) >= chunk_size:
                        try:
                            self.cursor.executemany(insert_query, batch_data)
                            self.connection.commit()
                            imported += len(batch_data)
                            batch_data = []
                        except mysql.connector.Error as e:
                            logger.error(f"Erreur insertion postal: {e}")
                            skipped += len(batch_data)
                            batch_data = []
                
                # Dernier batch
                if batch_data:
                    try:
                        self.cursor.executemany(insert_query, batch_data)
                        self.connection.commit()
                        imported += len(batch_data)
                    except mysql.connector.Error as e:
                        logger.error(f"Erreur insertion final postal: {e}")
                        skipped += len(batch_data)
            
            total_imported += imported
            total_skipped += skipped
            logger.info(f"✅ {postal_file.name}: {imported} importés, {skipped} ignorés")
        
        return total_imported, total_skipped
    
    def save_import_stats(self):
        """Sauvegarder les statistiques d'import"""
        for table, stats in self.stats.items():
            if stats['imported'] > 0 or stats['skipped'] > 0:
                self.cursor.execute("""
                    INSERT INTO import_stats (table_name, records_imported, records_skipped, notes)
                    VALUES (%s, %s, %s, %s)
                """, (table, stats['imported'], stats['skipped'], f"Import automatique"))
        
        self.connection.commit()
        logger.info("📊 Statistiques sauvegardées")
    
    def run_full_import(self):
        """Lancer l'import complet"""
        logger.info("🚀 Démarrage import complet")
        start_time = datetime.now()
        
        try:
            self.connect_db()
            
            # 1. Import UNESCO (nettoyé)
            unesco_file = self.data_path / 'unesco_heritage.txt'
            imported, skipped = self.import_geonames_file(unesco_file, 'unesco_sites')
            self.stats['unesco']['imported'] = imported
            self.stats['unesco']['skipped'] = skipped
            
            # 2. Import sites culturels
            cultural_file = self.data_path / 'cultural_sites_clean.txt'
            if cultural_file.exists():
                imported, skipped = self.import_geonames_file(cultural_file, 'cultural_sites')
                self.stats['cultural']['imported'] = imported
                self.stats['cultural']['skipped'] = skipped
            
            # 3. Import codes postaux
            imported, skipped = self.import_postal_codes()
            self.stats['postal']['imported'] = imported 
            self.stats['postal']['skipped'] = skipped
            
            # 4. Import GeoNames par pays (fichiers les plus gros)
            country_files = [f for f in self.data_path.glob("*.txt") 
                           if f.name.match(r'^[A-Z]{2}\.txt$')]
            
            total_geo_imported = 0
            total_geo_skipped = 0
            
            for country_file in country_files:
                imported, skipped = self.import_geonames_file(country_file, 'geonames')
                total_geo_imported += imported
                total_geo_skipped += skipped
            
            self.stats['geonames']['imported'] = total_geo_imported
            self.stats['geonames']['skipped'] = total_geo_skipped
            
            # 5. Sauvegarder stats
            self.save_import_stats()
            
            # 6. Rapport final
            duration = datetime.now() - start_time
            logger.info("🎉 Import terminé!")
            logger.info(f"⏱️  Durée: {duration}")
            logger.info("📊 Résumé:")
            for table, stats in self.stats.items():
                if stats['imported'] > 0:
                    logger.info(f"   {table}: {stats['imported']:,} importés, {stats['skipped']:,} ignorés")
            
        except Exception as e:
            logger.error(f"❌ Erreur durant l'import: {e}")
            raise
        finally:
            self.disconnect_db()


def main():
    """Point d'entrée principal"""
    parser = argparse.ArgumentParser(description="Import des données géographiques")
    parser.add_argument("--data-path", default="~/travel-specific", 
                       help="Chemin vers les données (défaut: ~/travel-specific)")
    parser.add_argument("--db-host", default="localhost", help="Host MySQL")
    parser.add_argument("--db-user", default="root", help="Utilisateur MySQL")
    parser.add_argument("--db-password", default="mysqlroot", help="Mot de passe MySQL")
    parser.add_argument("--db-name", default="immich_gallery", help="Nom de la base")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Taille des chunks")
    
    args = parser.parse_args()
    
    # Configuration DB
    db_config = {
        'host': args.db_host,
        'user': args.db_user,
        'password': args.db_password,
        'database': args.db_name,
        'charset': 'utf8mb4',
        'use_unicode': True,
        'autocommit': False
    }
    
    # Vérifier que le dossier de données existe
    data_path = Path(args.data_path).expanduser()
    if not data_path.exists():
        logger.error(f"❌ Dossier de données non trouvé: {data_path}")
        sys.exit(1)
    
    # Lancer l'import
    importer = GeoDataImporter(str(data_path), db_config)
    importer.run_full_import()


if __name__ == "__main__":
    main()