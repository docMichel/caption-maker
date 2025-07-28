-- Configuration base de données pour Caption Generator
-- Création des tables optimisées pour la géolocalisation
-- Usage: mysql -u root -p immich_gallery < mysql_setup.sql

-- ========================================
-- 1. TABLE PRINCIPALE GEONAMES
-- ========================================

DROP TABLE IF EXISTS geonames;

CREATE TABLE geonames (
    id INT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    ascii_name VARCHAR(200) NOT NULL,
    alternate_names TEXT,
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
    modification_date DATE,
    
    -- Index optimisés pour recherche géographique
    INDEX idx_country (country_code),
    INDEX idx_feature (feature_class, feature_code),
    INDEX idx_population (population),
    INDEX idx_coords (latitude, longitude),
    INDEX idx_name (name(50)),
    INDEX idx_search (country_code, feature_class, population DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 2. TABLE UNESCO SITES (nettoyée)
-- ========================================

DROP TABLE IF EXISTS unesco_sites;

CREATE TABLE unesco_sites (
    id INT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    ascii_name VARCHAR(200) NOT NULL,
    alternate_names TEXT,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    country_code CHAR(2) NOT NULL,
    admin1_code VARCHAR(20),
    category VARCHAR(50) DEFAULT 'heritage',
    description TEXT,
    elevation INT DEFAULT NULL,
    timezone VARCHAR(40),
    modification_date DATE,
    
    -- Index pour recherche UNESCO
    INDEX idx_unesco_country (country_code),
    INDEX idx_unesco_coords (latitude, longitude),
    INDEX idx_unesco_category (category),
    INDEX idx_unesco_name (name(50))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 3. TABLE SITES CULTURELS
-- ========================================

DROP TABLE IF EXISTS cultural_sites;

CREATE TABLE cultural_sites (
    id INT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    ascii_name VARCHAR(200) NOT NULL,
    alternate_names TEXT,
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    feature_class CHAR(1) NOT NULL,
    feature_code VARCHAR(10) NOT NULL,
    country_code CHAR(2) NOT NULL,
    admin1_code VARCHAR(20),
    admin2_code VARCHAR(20),
    site_type VARCHAR(50),
    elevation INT DEFAULT NULL,
    timezone VARCHAR(40),
    modification_date DATE,
    
    -- Index pour sites culturels
    INDEX idx_cultural_country (country_code),
    INDEX idx_cultural_coords (latitude, longitude),
    INDEX idx_cultural_type (site_type),
    INDEX idx_cultural_feature (feature_class, feature_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 4. TABLE DONNÉES POSTALES
-- ========================================

DROP TABLE IF EXISTS postal_codes;

CREATE TABLE postal_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    country_code CHAR(2) NOT NULL,
    postal_code VARCHAR(20) NOT NULL,
    place_name VARCHAR(180) NOT NULL,
    admin1_name VARCHAR(100),
    admin1_code VARCHAR(20),
    admin2_name VARCHAR(100),
    admin2_code VARCHAR(20),
    admin3_name VARCHAR(100),
    admin3_code VARCHAR(20),
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    accuracy TINYINT DEFAULT 1,
    
    -- Index pour codes postaux
    INDEX idx_postal_country (country_code),
    INDEX idx_postal_code (postal_code),
    INDEX idx_postal_coords (latitude, longitude),
    INDEX idx_postal_place (place_name(50)),
    UNIQUE KEY unique_postal (country_code, postal_code, place_name(50))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 5. TABLE STATISTIQUES IMPORT
-- ========================================

DROP TABLE IF EXISTS import_stats;

CREATE TABLE import_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    country_code CHAR(2),
    records_imported INT DEFAULT 0,
    records_skipped INT DEFAULT 0,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_source VARCHAR(100),
    notes TEXT,
    
    INDEX idx_stats_table (table_name),
    INDEX idx_stats_country (country_code),
    INDEX idx_stats_date (import_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 6. FONCTIONS UTILITAIRES
-- ========================================

-- Fonction pour calculer la distance en km entre deux points
DELIMITER //
CREATE FUNCTION haversine_distance(
    lat1 DECIMAL(10,7), 
    lon1 DECIMAL(10,7), 
    lat2 DECIMAL(10,7), 
    lon2 DECIMAL(10,7)
) RETURNS DECIMAL(10,3)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE earth_radius DECIMAL(10,3) DEFAULT 6371.0;
    DECLARE dlat DECIMAL(10,7);
    DECLARE dlon DECIMAL(10,7);
    DECLARE a DECIMAL(20,10);
    DECLARE c DECIMAL(20,10);
    
    SET dlat = RADIANS(lat2 - lat1);
    SET dlon = RADIANS(lon2 - lon1);
    SET a = SIN(dlat/2) * SIN(dlat/2) + 
            COS(RADIANS(lat1)) * COS(RADIANS(lat2)) * 
            SIN(dlon/2) * SIN(dlon/2);
    SET c = 2 * ATAN2(SQRT(a), SQRT(1-a));
    
    RETURN earth_radius * c;
END//
DELIMITER ;

-- ========================================
-- 7. VUES UTILES
-- ========================================

-- Vue des sites touristiques majeurs
CREATE OR REPLACE VIEW major_tourist_sites AS
SELECT 
    id,
    name,
    latitude,
    longitude,
    country_code,
    feature_code,
    population,
    'geonames' as source
FROM geonames 
WHERE feature_class = 'S' 
   AND feature_code IN ('HSTS', 'MUS', 'MNM', 'TMPL', 'PAL')
   AND population > 0

UNION ALL

SELECT 
    id,
    name,
    latitude,
    longitude,
    country_code,
    'UNESCO' as feature_code,
    0 as population,
    'unesco' as source
FROM unesco_sites;

-- Vue des villes importantes (> 1000 habitants)
CREATE OR REPLACE VIEW major_cities AS
SELECT 
    id,
    name,
    ascii_name,
    latitude,
    longitude,
    country_code,
    admin1_code,
    population,
    elevation
FROM geonames 
WHERE feature_class = 'P' 
   AND feature_code IN ('PPL', 'PPLA', 'PPLA2', 'PPLA3', 'PPLC')
   AND population >= 1000
ORDER BY population DESC;

-- ========================================
-- 8. PROCÉDURES STOCKÉES UTILES
-- ========================================

-- Procédure pour rechercher des sites proches
DELIMITER //
CREATE PROCEDURE find_nearby_sites(
    IN search_lat DECIMAL(10,7),
    IN search_lon DECIMAL(10,7),
    IN radius_km DECIMAL(10,3),
    IN max_results INT
)
BEGIN
    SELECT 
        g.id,
        g.name,
        g.latitude,
        g.longitude,
        g.country_code,
        g.feature_class,
        g.feature_code,
        g.population,
        haversine_distance(search_lat, search_lon, g.latitude, g.longitude) as distance_km,
        'geonames' as source
    FROM geonames g
    WHERE haversine_distance(search_lat, search_lon, g.latitude, g.longitude) <= radius_km
    
    UNION ALL
    
    SELECT 
        u.id,
        u.name,
        u.latitude,
        u.longitude,
        u.country_code,
        'S' as feature_class,
        'UNESCO' as feature_code,
        0 as population,
        haversine_distance(search_lat, search_lon, u.latitude, u.longitude) as distance_km,
        'unesco' as source
    FROM unesco_sites u
    WHERE haversine_distance(search_lat, search_lon, u.latitude, u.longitude) <= radius_km
    
    ORDER BY distance_km ASC
    LIMIT max_results;
END//
DELIMITER ;

-- ========================================
-- 9. CONFIGURATION FINALE
-- ========================================

-- Optimisations MySQL pour gros volumes
SET GLOBAL innodb_buffer_pool_size = 1073741824; -- 1GB si possible
SET GLOBAL innodb_log_file_size = 268435456;     -- 256MB
SET GLOBAL max_allowed_packet = 67108864;        -- 64MB

-- Messages de confirmation
SELECT 'Base de données configurée avec succès!' as status;
SELECT 'Tables créées: geonames, unesco_sites, cultural_sites, postal_codes, import_stats' as tables;
SELECT 'Fonctions créées: haversine_distance' as functions;
SELECT 'Procédures créées: find_nearby_sites' as procedures;
SELECT 'Vues créées: major_tourist_sites, major_cities' as views;