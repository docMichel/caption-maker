#!/usr/bin/env python3
"""
📍 src/services/immich_api_service.py

ImmichAPIService - Interface avec l'API Immich pour données faciales
Utilise le proxy local pour éviter les problèmes CORS
Enrichit les légendes avec contexte social (personnes identifiées)
"""

import requests
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import json
from pathlib import Path
import time

logger = logging.getLogger(__name__)

@dataclass
class FaceData:
    """Données d'un visage détecté"""
    face_id: str
    person_id: Optional[str] = None
    person_name: Optional[str] = None
    confidence: float = 0.0
    bounding_box: Dict[str, float] = None
    
    def __post_init__(self):
        if self.bounding_box is None:
            self.bounding_box = {}

@dataclass
class AssetFacesInfo:
    """Informations complètes sur les visages d'un asset"""
    asset_id: str
    faces: List[FaceData]
    total_faces: int
    identified_people: List[str]
    unknown_faces: int
    social_context: str  # "selfie", "portrait", "group", "family"
    
    def __post_init__(self):
        self.total_faces = len(self.faces)
        self.identified_people = [f.person_name for f in self.faces if f.person_name]
        self.unknown_faces = len([f for f in self.faces if not f.person_name])
        self.social_context = self._determine_social_context()
    
    def _determine_social_context(self) -> str:
        """Déterminer le contexte social basé sur le nombre de visages"""
        if self.total_faces == 0:
            return "landscape"
        elif self.total_faces == 1:
            return "selfie" if any("selfie" in (f.person_name or "").lower() for f in self.faces) else "portrait"
        elif self.total_faces <= 3:
            return "small_group"
        elif self.total_faces <= 6:
            return "group"
        else:
            return "large_group"

class ImmichAPIService:
    """
    Service d'interface avec l'API Immich
    Récupère les données de reconnaissance faciale pour enrichir les légendes
    """
    
    def __init__(self, proxy_url: str = "http://localhost:3001", api_key: str = None, 
                 timeout: int = 30):
        """
        Initialiser le service API Immich
        
        Args:
            proxy_url: URL du proxy Immich (défaut: localhost:3001)
            api_key: Clé API Immich
            timeout: Timeout des requêtes en secondes
        """
        self.proxy_url = proxy_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        
        # Headers pour les requêtes
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ImmichCaptionGenerator/1.0'
        }
        
        if self.api_key:
            self.headers['X-API-Key'] = self.api_key
        
        # Cache simple pour éviter les requêtes répétées
        self._faces_cache = {}
        self._people_cache = {}
        self._cache_ttl = 300  # 5 minutes
        
        # Statistiques d'utilisation
        self.stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'errors': 0,
            'assets_processed': 0
        }
        
        logger.info(f"🎭 ImmichAPIService initialisé (proxy: {self.proxy_url})")
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Tester la connexion à l'API Immich
        
        Returns:
            Dict avec statut de connexion et infos serveur
        """
        try:
            # Test avec endpoint de base (server info)
            response = self._make_request('GET', '/api/server-info')
            
            if response:
                logger.info("✅ Connexion Immich API réussie")
                return {
                    'connected': True,
                    'server_info': response,
                    'proxy_url': self.proxy_url,
                    'auth_configured': bool(self.api_key)
                }
            else:
                return {'connected': False, 'error': 'Pas de réponse du serveur'}
                
        except Exception as e:
            logger.error(f"❌ Erreur connexion Immich API: {e}")
            return {'connected': False, 'error': str(e)}
    
    def get_asset_faces(self, asset_id: str, use_cache: bool = True) -> Optional[AssetFacesInfo]:
        """
        Récupérer les informations de visages pour un asset
        
        Args:
            asset_id: ID de l'asset Immich
            use_cache: Utiliser le cache si disponible
            
        Returns:
            AssetFacesInfo ou None si erreur
        """
        # Vérifier le cache
        if use_cache and asset_id in self._faces_cache:
            cached_data, timestamp = self._faces_cache[asset_id]
            if time.time() - timestamp < self._cache_ttl:
                self.stats['cache_hits'] += 1
                logger.debug(f"📍 Cache hit pour asset {asset_id}")
                return cached_data
        
        logger.info(f"🎭 Récupération visages pour asset {asset_id}")
        self.stats['api_calls'] += 1
        
        try:
            # 1. Récupérer les données de l'asset
            asset_data = self._make_request('GET', f'/api/assets/{asset_id}')
            if not asset_data:
                logger.warning(f"⚠️  Asset {asset_id} non trouvé")
                return None
            
            # 2. Récupérer les visages de l'asset
            faces_data = self._get_asset_faces_data(asset_id)
            
            # 3. Récupérer les informations des personnes
            people_data = self._get_people_data()
            
            # 4. Construire les données de visages
            faces = []
            for face in faces_data:
                face_info = self._process_face_data(face, people_data)
                if face_info:
                    faces.append(face_info)
            
            # 5. Créer l'objet AssetFacesInfo
            asset_faces_info = AssetFacesInfo(
                asset_id=asset_id,
                faces=faces
            )
            
            # 6. Mettre en cache
            self._faces_cache[asset_id] = (asset_faces_info, time.time())
            self.stats['assets_processed'] += 1
            
            logger.info(f"   ✅ {len(faces)} visages trouvés (contexte: {asset_faces_info.social_context})")
            return asset_faces_info
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération visages pour {asset_id}: {e}")
            self.stats['errors'] += 1
            return None
    
    def _get_asset_faces_data(self, asset_id: str) -> List[Dict]:
        """Récupérer les données brutes des visages d'un asset"""
        # Endpoint pour récupérer les visages
        # Note: L'endpoint exact peut varier selon la version d'Immich
        faces_endpoints = [
            f'/api/faces?assetId={asset_id}',  # Endpoint moderne
            f'/api/assets/{asset_id}/faces',   # Endpoint alternatif
            f'/api/person/faces/{asset_id}'    # Endpoint legacy
        ]
        
        for endpoint in faces_endpoints:
            try:
                faces_data = self._make_request('GET', endpoint)
                if faces_data:
                    # Normaliser la structure selon le format de réponse
                    if isinstance(faces_data, list):
                        return faces_data
                    elif isinstance(faces_data, dict) and 'faces' in faces_data:
                        return faces_data['faces']
                    elif isinstance(faces_data, dict) and 'results' in faces_data:
                        return faces_data['results']
                    
            except Exception as e:
                logger.debug(f"Endpoint {endpoint} échoué: {e}")
                continue
        
        logger.warning(f"⚠️  Aucun endpoint de visages fonctionnel pour asset {asset_id}")
        return []
    
    def _get_people_data(self) -> Dict[str, Dict]:
        """Récupérer la liste des personnes connues avec cache"""
        if 'people' in self._people_cache:
            cached_people, timestamp = self._people_cache['people']
            if time.time() - timestamp < self._cache_ttl * 2:  # Cache plus long pour les personnes
                return cached_people
        
        try:
            people_response = self._make_request('GET', '/api/people')
            people_dict = {}
            
            if people_response:
                # Normaliser selon le format de l'API
                people_list = people_response
                if isinstance(people_response, dict):
                    people_list = people_response.get('people', people_response.get('results', []))
                
                for person in people_list:
                    person_id = person.get('id')
                    if person_id:
                        people_dict[person_id] = {
                            'name': person.get('name', f'Personne {person_id[:8]}'),
                            'face_count': person.get('faceCount', 0),
                            'thumbnail_path': person.get('thumbnailPath', '')
                        }
            
            # Mettre en cache
            self._people_cache['people'] = (people_dict, time.time())
            logger.debug(f"📊 {len(people_dict)} personnes en cache")
            
            return people_dict
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération personnes: {e}")
            return {}
    
    def _process_face_data(self, face_raw: Dict, people_data: Dict[str, Dict]) -> Optional[FaceData]:
        """Traiter les données brutes d'un visage"""
        try:
            face_id = face_raw.get('id', '')
            person_id = face_raw.get('personId') or face_raw.get('person_id')
            
            # Informations de la personne si identifiée
            person_name = None
            if person_id and person_id in people_data:
                person_name = people_data[person_id]['name']
            
            # Bounding box si disponible
            bbox = {}
            if 'boundingBoxX1' in face_raw:
                bbox = {
                    'x1': face_raw.get('boundingBoxX1', 0),
                    'y1': face_raw.get('boundingBoxY1', 0),
                    'x2': face_raw.get('boundingBoxX2', 0),
                    'y2': face_raw.get('boundingBoxY2', 0)
                }
            
            return FaceData(
                face_id=face_id,
                person_id=person_id,
                person_name=person_name,
                confidence=face_raw.get('confidence', 0.0),
                bounding_box=bbox
            )
            
        except Exception as e:
            logger.warning(f"⚠️  Erreur traitement visage: {e}")
            return None
    
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Faire une requête à l'API Immich via le proxy"""
        url = f"{self.proxy_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=self.headers, json=data, timeout=self.timeout)
            else:
                raise ValueError(f"Méthode HTTP non supportée: {method}")
            
            response.raise_for_status()
            
            # Essayer de parser le JSON
            try:
                return response.json()
            except json.JSONDecodeError:
                # Si ce n'est pas du JSON, retourner le texte
                return {'response': response.text}
                
        except requests.RequestException as e:
            logger.error(f"❌ Erreur requête {method} {endpoint}: {e}")
            return None
    
    def generate_face_context_for_ai(self, asset_faces_info: AssetFacesInfo) -> Dict[str, str]:
        """
        Générer un contexte textuel sur les visages pour l'IA
        
        Args:
            asset_faces_info: Informations sur les visages
            
        Returns:
            Dict avec différents niveaux de contexte
        """
        if not asset_faces_info or asset_faces_info.total_faces == 0:
            return {
                'face_context': '',
                'social_context': 'paysage',
                'people_list': '',
                'photo_type': 'landscape'
            }
        
        # Construire la liste des personnes
        people_names = [name for name in asset_faces_info.identified_people if name]
        people_text = ""
        
        if len(people_names) == 1:
            people_text = f"avec {people_names[0]}"
        elif len(people_names) == 2:
            people_text = f"avec {people_names[0]} et {people_names[1]}"
        elif len(people_names) > 2:
            people_text = f"avec {', '.join(people_names[:-1])} et {people_names[-1]}"
        elif asset_faces_info.unknown_faces > 0:
            if asset_faces_info.unknown_faces == 1:
                people_text = "portrait d'une personne"
            else:
                people_text = f"photo de groupe ({asset_faces_info.unknown_faces} personnes)"
        
        # Contexte social détaillé
        social_contexts = {
            'selfie': 'selfie',
            'portrait': 'portrait',
            'small_group': 'photo entre proches',
            'group': 'photo de groupe',
            'large_group': 'grande assemblée',
            'landscape': 'paysage'
        }
        
        social_description = social_contexts.get(asset_faces_info.social_context, 'photo')
        
        # Type de photo pour les prompts
        photo_types = {
            'selfie': 'selfie',
            'portrait': 'portrait',
            'small_group': 'group_photo',
            'group': 'group_photo',
            'large_group': 'event_photo',
            'landscape': 'landscape'
        }
        
        photo_type = photo_types.get(asset_faces_info.social_context, 'photo')
        
        return {
            'face_context': people_text,
            'social_context': social_description,
            'people_list': ', '.join(people_names) if people_names else '',
            'photo_type': photo_type,
            'face_count': str(asset_faces_info.total_faces),
            'identified_count': str(len(people_names)),
            'unknown_count': str(asset_faces_info.unknown_faces)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourner les statistiques d'utilisation"""
        return {
            **self.stats,
            'cache_size': len(self._faces_cache),
            'cache_hit_rate': (
                self.stats['cache_hits'] / max(self.stats['api_calls'], 1) * 100
            ) if self.stats['api_calls'] > 0 else 0,
            'proxy_url': self.proxy_url,
            'auth_configured': bool(self.api_key)
        }
    
    def clear_cache(self):
        """Vider le cache"""
        self._faces_cache.clear()
        self._people_cache.clear()
        logger.info("🗑️  Cache Immich vidé")


# Exemple d'utilisation et tests
if __name__ == "__main__":
    import logging
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    print("🎭 Test ImmichAPIService")
    print("=" * 40)
    
    # Configuration de test
    # IMPORTANT: Remplacez par votre vraie clé API
    API_KEY = "your-immich-api-key-here"
    
    if API_KEY == "your-immich-api-key-here":
        print("⚠️  Configurez votre clé API dans le script pour tester")
        exit(1)
    
    try:
        # Initialiser le service
        immich_service = ImmichAPIService(
            proxy_url="http://localhost:3001",
            api_key=API_KEY
        )
        
        # Test de connexion
        print("🔗 Test de connexion...")
        connection_test = immich_service.test_connection()
        
        if connection_test['connected']:
            print("✅ Connexion réussie!")
            print(f"   Serveur: {connection_test.get('server_info', {}).get('version', 'N/A')}")
        else:
            print(f"❌ Connexion échouée: {connection_test.get('error')}")
            exit(1)
        
        # Test avec un asset ID (remplacez par un vrai ID de votre instance)
        test_asset_id = "00000000-0000-0000-0000-000000000000"  # ID de test
        
        print(f"\n🎭 Test récupération visages pour asset: {test_asset_id}")
        faces_info = immich_service.get_asset_faces(test_asset_id)
        
        if faces_info:
            print(f"✅ Visages récupérés:")
            print(f"   Total visages: {faces_info.total_faces}")
            print(f"   Personnes identifiées: {len(faces_info.identified_people)}")
            print(f"   Contexte social: {faces_info.social_context}")
            
            if faces_info.identified_people:
                print(f"   Noms: {', '.join(faces_info.identified_people)}")
            
            # Test génération contexte pour IA
            ai_context = immich_service.generate_face_context_for_ai(faces_info)
            print(f"\n🤖 Contexte pour IA:")
            for key, value in ai_context.items():
                if value:
                    print(f"   {key}: {value}")
        else:
            print("⚠️  Aucun visage trouvé (ou asset inexistant)")
        
        # Statistiques
        stats = immich_service.get_stats()
        print(f"\n📊 Statistiques:")
        print(f"   Appels API: {stats['api_calls']}")
        print(f"   Cache hits: {stats['cache_hits']}")
        print(f"   Taux cache: {stats['cache_hit_rate']:.1f}%")
        print(f"   Erreurs: {stats['errors']}")
        
    except Exception as e:
        print(f"❌ Erreur durant les tests: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🎉 Test ImmichAPIService terminé!")