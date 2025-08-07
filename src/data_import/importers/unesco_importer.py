# src/data_import/importers/unesco_importer.py
import logging
import requests
import mysql.connector
import xml.etree.ElementTree as ET
import csv
import io
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class UNESCOImporter:
    def __init__(self, db_config):
        self.db_config = db_config
        # URL du fichier CSV officiel UNESCO
        self.csv_url = "https://whc.unesco.org/en/list/xml/whc-sites.xml"
        # Alternative : CSV direct
        self.csv_alt_url = "https://whc.unesco.org/en/list/?action=exportcsv&format=csv"
        
    def import_country(self, country_code: str) -> int:
        """Importer les sites UNESCO pour un pays"""
        logger.info(f"📥 Import UNESCO pour {country_code}")
        
        try:
            # 1. Télécharger toutes les données UNESCO
            all_sites = self._download_unesco_data()
            if not all_sites:
                logger.warning("   ⚠️ Aucune donnée UNESCO téléchargée")
                return 0
            
            # 2. Filtrer pour le pays
            country_sites = self._filter_by_country(all_sites, country_code)
            if not country_sites:
                logger.info(f"   ℹ️ Aucun site UNESCO pour {country_code}")
                return 0
            
            logger.info(f"   📍 {len(country_sites)} sites UNESCO trouvés pour {country_code}")
            
            # 3. Insérer dans la base
            return self._insert_sites(country_sites)
            
        except Exception as e:
            logger.error(f"❌ Erreur import UNESCO: {e}")
            import traceback
            traceback.print_exc()
            return 0
    
    def _download_unesco_data(self) -> List[Dict]:
        """Télécharger les données UNESCO depuis le XML officiel"""
        try:
            logger.info("   📥 Téléchargement données UNESCO...")
            
            # Essayer le XML
            response = requests.get(self.csv_url, timeout=30)
            response.raise_for_status()
            
            # Parser le XML
            root = ET.fromstring(response.content)
            
            sites = []
            for row in root.findall('.//row'):
                site_data = {}
                
                # Extraire les champs
                site_data['id_number'] = row.findtext('id_number', '')
                site_data['name'] = row.findtext('site', '')
                site_data['states'] = row.findtext('states_name_en', '')
                site_data['iso_code'] = row.findtext('iso_code', '')
                site_data['latitude'] = row.findtext('latitude')
                site_data['longitude'] = row.findtext('longitude')
                site_data['category'] = row.findtext('category', '')
                site_data['date_inscribed'] = row.findtext('date_inscribed', '')
                site_data['danger'] = row.findtext('danger', '0')
                site_data['area_hectares'] = row.findtext('area_hectares', '0')
                site_data['criteria_txt'] = row.findtext('criteria_txt', '')
                site_data['short_description'] = row.findtext('short_description_en', '')
                
                # Valider les coordonnées
                if site_data['latitude'] and site_data['longitude']:
                    try:
                        site_data['latitude'] = float(site_data['latitude'])
                        site_data['longitude'] = float(site_data['longitude'])
                        sites.append(site_data)
                    except ValueError:
                        logger.warning(f"   ⚠️ Coordonnées invalides pour {site_data['name']}")
                
            logger.info(f"   ✅ {len(sites)} sites UNESCO téléchargés")
            return sites
            
        except Exception as e:
            logger.error(f"   ❌ Erreur téléchargement XML: {e}")
            
            # Fallback : essayer le CSV
            return self._download_unesco_csv()
    
    def _download_unesco_csv(self) -> List[Dict]:
        """Alternative : télécharger le CSV"""
        try:
            logger.info("   📥 Tentative téléchargement CSV...")
            
            response = requests.get(self.csv_alt_url, timeout=30)
            response.raise_for_status()
            
            # Parser le CSV
            csv_content = io.StringIO(response.text)
            reader = csv.DictReader(csv_content)
            
            sites = []
            for row in reader:
                if row.get('latitude') and row.get('longitude'):
                    try:
                        site_data = {
                            'id_number': row.get('id_no', ''),
                            'name': row.get('name_en', ''),
                            'states': row.get('states_name_en', ''),
                            'iso_code': row.get('iso_code', ''),
                            'latitude': float(row.get('latitude', 0)),
                            'longitude': float(row.get('longitude', 0)),
                            'category': row.get('category', ''),
                            'date_inscribed': row.get('date_inscribed', ''),
                            'danger': row.get('danger', '0'),
                            'area_hectares': row.get('area_hectares', '0'),
                            'criteria_txt': row.get('criteria_txt', ''),
                            'short_description': row.get('short_description_en', '')
                        }
                        sites.append(site_data)
                    except ValueError:
                        continue
            
            return sites
            
        except Exception as e:
            logger.error(f"   ❌ Erreur téléchargement CSV: {e}")
            return []
    
    def _filter_by_country(self, sites: List[Dict], country_code: str) -> List[Dict]:
        """Filtrer les sites par code pays"""
        # Mapping des codes spéciaux
        country_mapping = {
            'NC': ['fr', 'france', 'new caledonia'],  # Nouvelle-Calédonie
            'PF': ['fr', 'france', 'french polynesia'],
            'GP': ['fr', 'france', 'guadeloupe'],
            'MQ': ['fr', 'france', 'martinique'],
            'RE': ['fr', 'france', 'reunion'],
            'GF': ['fr', 'france', 'french guiana']
        }
        
        filtered = []
        
        for site in sites:
            site_iso = site.get('iso_code', '').lower()
            site_states = site.get('states', '').lower()
            
            # Vérification directe du code ISO
            if site_iso == country_code.lower():
                filtered.append(site)
                continue
            
            # Vérification pour les territoires
            if country_code in country_mapping:
                for keyword in country_mapping[country_code]:
                    if keyword in site_iso or keyword in site_states:
                        # Vérifier aussi le nom pour les territoires français
                        site_name_lower = site.get('name', '').lower()
                        territory_keywords = {
                            'NC': ['caledonia', 'calédonie'],
                            'PF': ['polynesia', 'polynésie', 'tahiti'],
                            'GP': ['guadeloupe'],
                            'MQ': ['martinique'],
                            'RE': ['reunion', 'réunion']
                        }
                        
                        if country_code in territory_keywords:
                            for territory_kw in territory_keywords[country_code]:
                                if territory_kw in site_name_lower or territory_kw in site_states:
                                    filtered.append(site)
                                    break
                        break
        
        return filtered
    
    def _insert_sites(self, sites: List[Dict]) -> int:
        """Insérer les sites UNESCO dans la base"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        
        try:
            # Créer/mettre à jour la table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS unesco_sites (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    unesco_id VARCHAR(20),
                    name VARCHAR(500) NOT NULL,
                    name_fr VARCHAR(500),
                    latitude DECIMAL(10, 7) NOT NULL,
                    longitude DECIMAL(10, 7) NOT NULL,
                    country VARCHAR(200),
                    country_code CHAR(2),
                    category VARCHAR(50),
                    date_inscribed INT,
                    danger_list BOOLEAN DEFAULT FALSE,
                    area_hectares DECIMAL(12, 2),
                    criteria VARCHAR(50),
                    description TEXT,
                    UNIQUE KEY idx_unesco_id (unesco_id),
                    INDEX idx_coords (latitude, longitude),
                    INDEX idx_country (country_code),
                    INDEX idx_category (category)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            # Préparer l'insertion
            insert_query = """
                INSERT INTO unesco_sites 
                (unesco_id, name, latitude, longitude, country, country_code, 
                 category, date_inscribed, danger_list, area_hectares, 
                 criteria, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    name = VALUES(name),
                    latitude = VALUES(latitude),
                    longitude = VALUES(longitude),
                    danger_list = VALUES(danger_list),
                    description = VALUES(description)
            """
            
            count = 0
            for site in sites:
                try:
                    logger.debug(f"   Insertion site: {site.get('name')} - {site.get('iso_code')}")

                    # Extraire l'année d'inscription
                    year = None
                    if site.get('date_inscribed'):
                        try:
                            year = int(site['date_inscribed'][:4])
                        except:
                            pass
                    
                    # Déterminer le code pays
                    iso_code = site.get('iso_code', '').upper()[:2]
                    
                    # Convertir area en nombre
                    area = None
                    if site.get('area_hectares'):
                        try:
                            area = float(site['area_hectares'].replace(',', ''))
                        except:
                            pass
                    
                    values = (
                        site.get('id_number'),
                        site.get('name')[:500],
                        site.get('latitude'),
                        site.get('longitude'),
                        site.get('states')[:200],
                        iso_code,
                        site.get('category', 'Cultural'),
                        year,
                        site.get('danger') == '1',
                        area,
                        site.get('criteria_txt', '')[:50],
                        site.get('short_description', '')
                    )
                    
                    cursor.execute(insert_query, values)
                    if cursor.rowcount > 0:
                        count += 1
                    else:
                       logger.warning(f"   ⚠️ Aucune ligne insérée pour {site.get('name')}")
                

                except Exception as e:
                    logger.warning(f"   ⚠️ Erreur insertion site {site.get('name')}: {e}")
                    logger.debug(f"      Valeurs: {values}")

                    continue
            
            conn.commit()
            logger.info(f"   ✅ {count} sites UNESCO insérés/mis à jour")
            return count
            
        finally:
            cursor.close()
            conn.close()