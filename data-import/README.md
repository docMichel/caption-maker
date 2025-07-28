# Scripts d'Import de Données Géographiques

Ce dossier contient les scripts pour importer et nettoyer les données géographiques dans MySQL.

## 📁 Structure

```
scripts/data-import/
├── mysql_setup.sql      # Configuration des tables MySQL
├── import_geonames.py   # Script d'import principal
└── README.md           # Cette documentation
```

## 🚀 Installation Rapide

### 1. Préparer MySQL

```bash
# Démarrer MySQL
brew services start mysql

# Se connecter et configurer
mysql -u root -p

# Dans MySQL:
CREATE DATABASE immich_gallery CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Créer les tables

```bash
cd ~/caption-maker/scripts/data-import

# Créer toutes les tables optimisées
mysql -u root -p immich_gallery < mysql_setup.sql
```

### 3. Lancer l'import

```bash
# Import complet avec paramètres par défaut
python3 import_geonames.py

# Ou avec paramètres personnalisés
python3 import_geonames.py \
  --data-path ~/travel-specific \
  --db-password "votre_mot_de_passe" \
  --chunk-size 2000
```

## 📊 Tables Créées

### `geonames` - Données géographiques principales
- **Sources**: Fichiers par pays (ID.txt, TH.txt, etc.)
- **Contenu**: Villes, montagnes, rivières, sites touristiques
- **Index**: Optimisés pour recherche par coordonnées et pays

### `unesco_sites` - Sites UNESCO (nettoyés)
- **Source**: unesco_heritage.txt (hôtels exclus!)
- **Contenu**: Sites du patrimoine mondial authentiques
- **Filtres**: Exclusion automatique des POI commerciaux

### `cultural_sites` - Sites culturels
- **Source**: cultural_sites_clean.txt
- **Contenu**: Monuments, musées, temples, sites archéologiques
- **Types**: HSTS, MUS, MNM, TMPL, PAL, ARCH

### `postal_codes` - Codes postaux
- **Sources**: Fichiers *_postal.txt
- **Contenu**: Correspondance code postal ↔ coordonnées
- **Usage**: Géolocalisation précise par adresse

### `import_stats` - Statistiques d'import
- **Suivi**: Nombre d'enregistrements importés/ignorés
- **Historique**: Date et source de chaque import

## 🔧 Fonctions Utilitaires

### `haversine_distance(lat1, lon1, lat2, lon2)`
Calcule la distance en km entre deux points GPS.

```sql
SELECT haversine_distance(-22.2697, 166.4381, -21.1775, 165.3181) as distance_km;
-- Résultat: distance entre Nouméa et Koné
```

### `find_nearby_sites(lat, lon, radius_km, max_results)`
Trouve tous les sites dans un rayon donné.

```sql
CALL find_nearby_sites(-22.2697, 166.4381, 50, 10);
-- Sites dans un rayon de 50km autour de Nouméa
```

## 📈 Vues Prêtes à l'Emploi

### `major_tourist_sites`
Combine GeoNames + UNESCO pour les sites touristiques majeurs.

### `major_cities`
Villes importantes (> 1000 habitants) triées par population.

## ⚙️ Options du Script

```bash
python3 import_geonames.py --help

Options:
  --data-path     Chemin vers les données (défaut: ~/travel-specific)
  --db-host       Host MySQL (défaut: localhost)
  --db-user       Utilisateur MySQL (défaut: root)
  --db-password   Mot de passe MySQL (défaut: mysqlroot)
  --db-name       Nom de la base (défaut: immich_gallery)
  --chunk-size    Taille des lots d'insertion (défaut: 1000)
```

## 📝 Logs et Monitoring

Le script génère automatiquement :
- **Logs détaillés**: `import_geonames.log`
- **Barre de progression**: Pour chaque fichier importé
- **Statistiques finales**: Résumé dans la console et en base

## 🧹 Nettoyage Automatique

### Données Exclues
- ❌ Hôtels dans unesco_heritage.txt
- ❌ Coordonnées invalides (hors limites mondiales)
- ❌ Lignes malformées ou incomplètes
- ❌ Doublons (grâce à INSERT IGNORE)

### Données Nettoyées
- ✅ Noms limités à 200 caractères
- ✅ Populations converties en entiers
- ✅ Élévations nulles si = -9999
- ✅ Dates formatées correctement

## 🚀 Performance

### Optimisations
- **Insertion par chunks** (1000 par défaut)
- **Index spatiaux** pour recherche rapide
- **INSERT IGNORE** pour éviter les doublons
- **Encodage UTF-8** pour caractères internationaux

### Temps d'Import Estimés (M4)
- **Codes postaux**: 2-3 minutes
- **UNESCO + Cultural**: 1 minute  
- **GeoNames pays**: 5-15 minutes selon la taille
- **Total**: 20-30 minutes pour dataset complet

## 🔍 Requêtes d'Exemple

### Sites UNESCO près d'une coordonnée
```sql
SELECT name, latitude, longitude, 
       haversine_distance(-22.2697, 166.4381, latitude, longitude) as distance_km
FROM unesco_sites 
WHERE haversine_distance(-22.2697, 166.4381, latitude, longitude) < 100
ORDER BY distance_km;
```

### Villes importantes d'un pays
```sql
SELECT name, population, latitude, longitude
FROM major_cities 
WHERE country_code = 'NC'
ORDER BY population DESC 
LIMIT 10;
```

### Statistiques par pays
```sql
SELECT country_code, 
       COUNT(*) as total_sites,
       COUNT(CASE WHEN feature_class = 'P' THEN 1 END) as cities,
       COUNT(CASE WHEN feature_class = 'S' THEN 1 END) as sites
FROM geonames 
GROUP BY country_code 
ORDER BY total_sites DESC;
```

## 🐛 Dépannage

### Erreur "Table doesn't exist"
```bash
# Recréer les tables
mysql -u root -p immich_gallery < mysql_setup.sql
```

### Erreur d'encodage
```bash
# Vérifier l'encodage des fichiers
file -bi ~/travel-specific/*.txt

# Forcer l'encodage UTF-8 si nécessaire
iconv -f ISO-8859-1 -t UTF-8 fichier.txt > fichier_utf8.txt
```

### Performance lente
```bash
# Augmenter la taille des chunks
python3 import_geonames.py --chunk-size 5000

# Ou optimiser MySQL
mysql -u root -p -e "SET GLOBAL innodb_buffer_pool_size = 2147483648;"
```

## 📞 Support

Si vous rencontrez des problèmes :

1. **Vérifiez les logs**: `import_geonames.log`
2. **Testez la connexion MySQL**: `mysql -u root -p immich_gallery`
3. **Vérifiez les fichiers source**: `ls -la ~/travel-specific/`
4. **Consultez les stats**: `SELECT * FROM import_stats ORDER BY import_date DESC;`

---

## 📈 Prochaines Étapes

Une fois l'import terminé, vous pourrez :

1. **Développer le GeoService** pour utiliser ces données
2. **Créer des API** de géolocalisation rapides
3. **Intégrer avec Immich** pour enrichir les métadonnées photos
4. **Ajouter de nouveaux pays** en plaçant simplement les fichiers dans le dossier

🎉 **Votre base géographique est maintenant prête pour alimenter les légendes intelligentes !**