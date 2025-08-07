# src/data_import/importers/unesco_importer.py
import logging

logger = logging.getLogger(__name__)

class UNESCOImporter:
    def __init__(self, db_config):
        self.db_config = db_config
        
    def import_country(self, country_code: str) -> int:
        logger.info(f"📥 Import UNESCO pour {country_code} (pas encore implémenté)")
        return 0