#!/usr/bin/env python3
"""
📍 src/services/ai_service.py

AIService - Orchestrateur IA pour génération de légendes contextuelles
Combine analyse d'image (LLaVA) + contexte géographique + génération créative (Mistral/Qwen2)
Utilise configuration externalisée pour flexibilité maximale
"""

import requests
import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
import base64
from dataclasses import dataclass
import sys

# Import du gestionnaire de config
sys.path.append(str(Path(__file__).parent.parent))
from config.ai_config import AIConfig
from .geo_service import GeoService, GeoLocation

logger = logging.getLogger(__name__)

@dataclass
class CaptionResult:
    """Résultat de génération de légende"""
    caption: str
    language: str
    style: str
    confidence_score: float
    generation_time_seconds: float
    
    # Métadonnées sources
    image_analysis: Dict[str, Any]
    geo_context: Dict[str, Any] 
    ai_models_used: List[str]
    
    # Debug info
    processing_steps: List[str]
    prompts_used: Dict[str, str] = None
    error_messages: List[str] = None
    
    def __post_init__(self):
        if self.error_messages is None:
            self.error_messages = []
        if self.prompts_used is None:
            self.prompts_used = {}

class AIService:
    """
    Service d'IA orchestrateur pour génération de légendes intelligentes
    
    Pipeline de traitement:
    1. Analyse visuelle de l'image (LLaVA)
    2. Enrichissement géographique (GeoService) 
    3. Génération créative de légende (Mistral/Qwen2)
    4. Post-traitement selon configuration
    """
    
    def __init__(self, geo_service: GeoService, config_path: Optional[str] = None):
        """
        Initialiser le service IA
        
        Args:
            geo_service: Instance du service de géolocalisation
            config_path: Chemin vers le fichier de config YAML (optionnel)
        """
        self.geo_service = geo_service
        
        # Charger la configuration externalisée
        self.config = AIConfig(config_path)
        
        # Configuration Ollama depuis le fichier
        ollama_config = self.config.get_ollama_config()
        self.ollama_base_url = ollama_config['base_url']
        self.ollama_timeout = ollama_config['timeout']
        self.default_temperature = ollama_config['default_temperature']
        self.max_retries = ollama_config['max_retries']
        
        # Modèles depuis configuration
        self.models = self.config.get_models()
        
        # Configuration debug
        self.debug_config = self.config.get_debug_config()
        
        # Statistiques d'utilisation
        self.stats = {
            'total_requests': 0,
            'successful_generations': 0,
            'failed_generations': 0,
            'average_processing_time': 0.0,
            'models_usage': {model: 0 for model in self.models.values()},
            'languages_used': {},
            'styles_used': {}
        }
        
        logger.info(f"🤖 AIService initialisé avec config: {self.config.export_config_summary()}")
    
    def generate_caption(self, image_path: str, latitude: float, longitude: float,
                        language: str = 'français', style: str = 'creative') -> CaptionResult:
        """
        Génération complète de légende contextuelle
        
        Args:
            image_path: Chemin vers l'image à analyser
            latitude, longitude: Coordonnées GPS
            language: Langue de génération (voir config pour langues supportées)
            style: Style de légende (voir config pour styles supportés)
            
        Returns:
            CaptionResult avec légende et métadonnées complètes
        """
        start_time = time.time()
        processing_steps = []
        prompts_used = {}
        self.stats['total_requests'] += 1
        
        # Validation des paramètres
        if not self.config.is_valid_language(language):
            logger.warning(f"⚠️  Langue non supportée '{language}', utilisation du français")
            language = 'français'
        
        if not self.config.is_valid_style(style):
            logger.warning(f"⚠️  Style non supporté '{style}', utilisation de 'creative'")
            style = 'creative'
        
        # Mise à jour des stats
        self.stats['languages_used'][language] = self.stats['languages_used'].get(language, 0) + 1
        self.stats['styles_used'][style] = self.stats['styles_used'].get(style, 0) + 1
        
        logger.info(f"🎨 Génération légende pour {Path(image_path).name} ({latitude:.4f}, {longitude:.4f})")
        logger.info(f"   Paramètres: {language} / {style}")
        
        try:
            # 1. Vérifier que l'image existe
            image_path = Path(image_path)
            if not image_path.exists():
                raise FileNotFoundError(f"Image non trouvée: {image_path}")
            
            processing_steps.append("✅ Image validée")
            
            # 2. Analyse visuelle avec LLaVA
            logger.info("   🔍 Analyse visuelle...")
            image_analysis = self._analyze_image_with_llava(image_path, prompts_used)
            processing_steps.append("✅ Analyse visuelle terminée")
            
            # 3. Récupération contexte géographique
            logger.info("   🌍 Enrichissement géographique...")
            geo_location = self.geo_service.get_location_info(latitude, longitude)
            geo_summary = self.geo_service.get_location_summary_for_ai(geo_location)
            processing_steps.append("✅ Contexte géographique récupéré")
            
            # 4. Enrichissement culturel avec Qwen2 (si pertinent)
            enriched_context = geo_summary.copy()
            if geo_location.confidence_score > 0.5 and geo_summary.get('cultural_context'):
                logger.info("   📚 Enrichissement culturel...")
                cultural_enrichment = self._enrich_cultural_context(geo_summary, prompts_used)
                if cultural_enrichment:
                    enriched_context['cultural_enrichment'] = cultural_enrichment
                    processing_steps.append("✅ Enrichissement culturel ajouté")
            
            # 5. Génération de la légende créative
            logger.info("   ✍️ Génération créative...")
            caption = self._generate_creative_caption(
                image_analysis['description'], 
                enriched_context, 
                language,
                style,
                prompts_used
            )
            processing_steps.append("✅ Légende générée")
            
            # 6. Post-traitement selon configuration
            original_caption = caption
            caption = self.config.clean_caption(caption)
            if caption != original_caption:
                processing_steps.append("✅ Post-traitement appliqué")
            
            # 7. Calcul du score de confiance
            confidence_score = self._calculate_confidence_score(
                image_analysis, geo_location, caption
            )
            
            generation_time = time.time() - start_time
            self._update_success_stats(generation_time)
            
            logger.info(f"   🎉 Légende générée en {generation_time:.1f}s (confiance: {confidence_score:.2f})")
            
            return CaptionResult(
                caption=caption,
                language=language,
                style=style,
                confidence_score=confidence_score,
                generation_time_seconds=generation_time,
                image_analysis=image_analysis,
                geo_context=geo_location.to_dict(),
                ai_models_used=list(self.models.values()),
                processing_steps=processing_steps,
                prompts_used=prompts_used if self.debug_config.get('log_prompts') else {}
            )
            
        except Exception as e:
            return self._handle_generation_error(e, language, latitude, longitude, 
                                               start_time, processing_steps, prompts_used)
    
    def _analyze_image_with_llava(self, image_path: Path, prompts_used: Dict[str, str]) -> Dict[str, Any]:
        """Analyser l'image avec le modèle LLaVA"""
        try:
            # Récupérer le prompt depuis la config
            prompt = self.config.get_image_analysis_prompt(detailed=False)
            params = self.config.get_image_analysis_params()
            
            if self.debug_config.get('log_prompts'):
                prompts_used['image_analysis'] = prompt
            
            # Encoder l'image en base64
            with open(image_path, 'rb') as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Préparer la requête Ollama
            payload = {
                'model': self.models['vision'],
                'prompt': prompt,
                'images': [image_base64],
                'stream': False,
                'options': {
                    'temperature': params.get('temperature', 0.6),
                    'num_predict': params.get('max_tokens', 200),
                    'top_p': params.get('top_p', 0.9)
                }
            }
            
            # Appel avec retry
            response = self._call_ollama_with_retry('generate', payload)
            
            if not response:
                raise ValueError("Pas de réponse d'Ollama")
            
            description = response.get('response', '').strip()
            
            if not description:
                raise ValueError("Réponse LLaVA vide")
            
            self.stats['models_usage'][self.models['vision']] += 1
            
            if self.debug_config.get('log_responses'):
                logger.debug(f"LLaVA response: {description}")
            
            return {
                'description': description,
                'confidence': 0.8,  # Score fixe pour LLaVA, ajustable dans config
                'model_used': self.models['vision'],
                'processing_time': response.get('total_duration', 0) / 1e9  # ns -> s
            }
            
        except Exception as e:
            logger.error(f"Erreur analyse LLaVA: {e}")
            return {
                'description': 'Image analysée automatiquement',
                'confidence': 0.3,
                'model_used': 'fallback',
                'error': str(e)
            }
    
    def _enrich_cultural_context(self, geo_summary: Dict[str, str], prompts_used: Dict[str, str]) -> Optional[str]:
        """Enrichir le contexte géographique avec informations culturelles"""
        try:
            # Déterminer si on utilise le prompt court ou long
            has_rich_context = bool(geo_summary.get('cultural_context') and 
                                  len(geo_summary.get('cultural_context', '')) > 50)
            
            prompt = self.config.get_cultural_enrichment_prompt(short=not has_rich_context)
            params = self.config.get_cultural_enrichment_params()
            
            # Formatter le prompt avec les données géo
            formatted_prompt = prompt.format(
                location_basic=geo_summary.get('location_basic', ''),
                current_context=geo_summary.get('cultural_context', '')
            )
            
            if self.debug_config.get('log_prompts'):
                prompts_used['cultural_enrichment'] = formatted_prompt
            
            response = self._call_ollama_text(
                self.models['geo_enrichment'], 
                formatted_prompt,
                max_tokens=params.get('max_tokens', 120),
                temperature=params.get('temperature', 0.5)
            )
            
            if response and len(response.strip()) > 20:
                self.stats['models_usage'][self.models['geo_enrichment']] += 1
                
                if self.debug_config.get('log_responses'):
                    logger.debug(f"Cultural enrichment: {response[:100]}...")
                
                return response.strip()
            
            return None
            
        except Exception as e:
            logger.warning(f"Erreur enrichissement culturel: {e}")
            return None
    
    def _generate_creative_caption(self, image_description: str, geo_context: Dict[str, str],
                                 language: str, style: str, prompts_used: Dict[str, str]) -> str:
        """Générer la légende créative avec le modèle configuré"""
        try:
            # Récupérer le template depuis la config
            prompt_template = self.config.get_caption_prompt(language, style)
            
            # Préparer les données pour le template
            template_data = {
                'image_description': image_description,
                'location_basic': geo_context.get('location_basic', 'lieu inconnu'),
                'cultural_context': geo_context.get('cultural_context', ''),
                'nearby_attractions': geo_context.get('nearby_attractions', ''),
                'cultural_enrichment': geo_context.get('cultural_enrichment', ''),
                'geographic_context': geo_context.get('geographic_context', '')
            }
            
            # Formatter le prompt
            formatted_prompt = prompt_template.format(**template_data)
            
            if self.debug_config.get('log_prompts'):
                prompts_used['caption_generation'] = formatted_prompt
            
            # Générer avec le modèle de légendes
            caption = self._call_ollama_text(
                self.models['caption'], 
                formatted_prompt, 
                max_tokens=250,
                temperature=0.8
            )
            
            if not caption:
                raise ValueError("Réponse du modèle de légende vide")
            
            self.stats['models_usage'][self.models['caption']] += 1
            
            if self.debug_config.get('log_responses'):
                logger.debug(f"Generated caption: {caption[:100]}...")
            
            return caption.strip()
            
        except Exception as e:
            logger.error(f"Erreur génération créative: {e}")
            # Fallback depuis la config
            return self.config.get_fallback_message(language, 'generic_error').format(
                location_basic=geo_context.get('location_basic', 'ce lieu')
            )
    
    def _call_ollama_text(self, model: str, prompt: str, max_tokens: int = 150, 
                         temperature: float = None) -> Optional[str]:
        """Appel générique à un modèle Ollama pour génération de texte"""
        if temperature is None:
            temperature = self.default_temperature
        
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens
            }
        }
        
        response = self._call_ollama_with_retry('generate', payload)
        return response.get('response', '').strip() if response else None
    
    def _call_ollama_with_retry(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Appel Ollama avec retry automatique"""
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.ollama_base_url}/api/{endpoint}",
                    json=payload,
                    timeout=self.ollama_timeout
                )
                response.raise_for_status()
                return response.json()
                
            except requests.RequestException as e:
                logger.warning(f"Tentative {attempt + 1}/{self.max_retries} échouée: {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"Échec définitif appel Ollama après {self.max_retries} tentatives")
                    return None
                time.sleep(1)  # Attendre avant retry
        
        return None
    
    def _calculate_confidence_score(self, image_analysis: Dict, geo_location: GeoLocation, 
                                  caption: str) -> float:
        """Calculer un score de confiance global selon la configuration"""
        quality_config = self.config.get_quality_scoring_config()
        weights = quality_config['weights']
        
        confidence = 0.0
        
        # Score de l'analyse d'image
        image_confidence = image_analysis.get('confidence', 0.5)
        confidence += image_confidence * weights['image_analysis']
        
        # Score de géolocalisation
        geo_confidence = min(geo_location.confidence_score, 1.0)
        confidence += geo_confidence * weights['geo_context']
        
        # Score de qualité de la légende (depuis config)
        caption_quality = self.config.calculate_caption_quality_score(caption)
        confidence += caption_quality * weights['caption_quality']
        
        return min(confidence, 1.0)
    
    def _update_success_stats(self, generation_time: float):
        """Mettre à jour les statistiques de succès"""
        self.stats['successful_generations'] += 1
        
        # Calcul de la moyenne mobile du temps de traitement
        prev_avg = self.stats['average_processing_time']
        success_count = self.stats['successful_generations']
        
        self.stats['average_processing_time'] = (
            (prev_avg * (success_count - 1) + generation_time) / success_count
        )
    
    def _handle_generation_error(self, error: Exception, language: str, latitude: float, longitude: float,
                                start_time: float, processing_steps: List[str], 
                                prompts_used: Dict[str, str]) -> CaptionResult:
        """Gérer les erreurs de génération avec fallback intelligent"""
        self.stats['failed_generations'] += 1
        error_msg = f"Erreur génération légende: {error}"
        logger.error(f"   ❌ {error_msg}")
        
        # Sauvegarder l'erreur si configuré
        if self.debug_config.get('save_failed_generations'):
            self._save_failed_generation(error_msg, language, latitude, longitude, prompts_used)
        
        # Message de fallback depuis la config
        fallback_caption = self.config.get_fallback_message(language, 'generic_error')
        
        return CaptionResult(
            caption=fallback_caption,
            language=language,
            style='fallback',
            confidence_score=0.1,
            generation_time_seconds=time.time() - start_time,
            image_analysis={'description': 'Analyse échouée', 'confidence': 0.0},
            geo_context={'error': str(error)},
            ai_models_used=[],
            processing_steps=processing_steps,
            prompts_used=prompts_used,
            error_messages=[error_msg]
        )
    
    def _save_failed_generation(self, error_msg: str, language: str, latitude: float, 
                              longitude: float, prompts_used: Dict[str, str]):
        """Sauvegarder les générations échouées pour debug"""
        try:
            log_dir = Path(__file__).parent.parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            
            log_file = log_dir / "failed_generations.jsonl"
            
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'error': error_msg,
                'language': language,
                'coordinates': [latitude, longitude],
                'prompts_used': prompts_used
            }
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder l'erreur: {e}")
    
    # =================================================================
    # MÉTHODES PUBLIQUES D'UTILITÉ
    # =================================================================
    
    def reload_config(self):
        """Recharger la configuration depuis le fichier"""
        logger.info("🔄 Rechargement configuration AIService...")
        self.config.reload_config()
        
        # Mettre à jour les paramètres
        ollama_config = self.config.get_ollama_config()
        self.ollama_base_url = ollama_config['base_url']
        self.ollama_timeout = ollama_config['timeout']
        self.default_temperature = ollama_config['default_temperature']
        self.max_retries = ollama_config['max_retries']
        
        self.models = self.config.get_models()
        self.debug_config = self.config.get_debug_config()
        
        logger.info("✅ Configuration rechargée")
    
    def get_available_models(self) -> Dict[str, List[str]]:
        """Récupérer la liste des modèles Ollama disponibles"""
        try:
            response = requests.get(f"{self.ollama_base_url}/api/tags", timeout=10)
            response.raise_for_status()
            
            data = response.json()
            available_models = [model['name'] for model in data.get('models', [])]
            configured_models = list(self.models.values())
            
            return {
                'available': available_models,
                'configured': configured_models,
                'missing': [model for model in configured_models if model not in available_models]
            }
            
        except Exception as e:
            logger.error(f"Erreur récupération modèles: {e}")
            return {'available': [], 'configured': list(self.models.values()), 'error': str(e)}
    
    def get_supported_options(self) -> Dict[str, List[str]]:
        """Récupérer les options supportées (langues, styles)"""
        return {
            'languages': [lang['code'] for lang in self.config.get_supported_languages()],
            'styles': [style['name'] for style in self.config.get_supported_styles()],
            'language_details': self.config.get_supported_languages(),
            'style_details': self.config.get_supported_styles()
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourner les statistiques d'utilisation détaillées"""
        total_requests = max(self.stats['total_requests'], 1)
        
        return {
            **self.stats,
            'success_rate': (self.stats['successful_generations'] / total_requests * 100),
            'failure_rate': (self.stats['failed_generations'] / total_requests * 100),
            'models_configured': self.models,
            'config_summary': self.config.export_config_summary(),
            'geo_service_cache': self.geo_service.get_cache_stats()
        }
    
    def test_pipeline(self, test_image_path: str = None) -> Dict[str, Any]:
        """Tester le pipeline complet avec validation de configuration"""
        logger.info("🧪 Test complet du pipeline AIService")
        
        # 1. Vérifier la configuration
        config_valid = True
        config_issues = []
        
        # Vérifier les modèles disponibles
        models_status = self.get_available_models()
        if models_status.get('missing'):
            config_issues.append(f"Modèles manquants: {models_status['missing']}")
            config_valid = False
        
        # Vérifier la connectivité Ollama
        try:
            requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
        except Exception as e:
            config_issues.append(f"Ollama inaccessible: {e}")
            config_valid = False
        
        # 2. Test avec image
        test_coords = (13.4125, 103.8667)  # Angkor Wat
        
        if not test_image_path:
            test_image_path = self._create_test_image()
        
        start_time = time.time()
        
        try:
            result = self.generate_caption(
                test_image_path, 
                test_coords[0], 
                test_coords[1],
                language='français',
                style='creative'
            )
            
            test_successful = len(result.error_messages) == 0
            
        except Exception as e:
            test_successful = False
            result = None
            config_issues.append(f"Erreur test pipeline: {e}")
        
        test_duration = time.time() - start_time
        
        return {
            'config_valid': config_valid,
            'config_issues': config_issues,
            'test_successful': test_successful,
            'test_duration_seconds': test_duration,
            'result': {
                'caption': result.caption if result else None,
                'confidence': result.confidence_score if result else 0.0,
                'models_used': result.ai_models_used if result else [],
                'processing_steps': result.processing_steps if result else []
            } if result else None,
            'errors': result.error_messages if result else [],
            'models_status': models_status,
            'supported_options': self.get_supported_options()
        }
    
    def _create_test_image(self) -> str:
        """Créer une image de test simple"""
        try:
            from PIL import Image
            import tempfile
            
            # Créer une image simple (rouge)
            img = Image.new('RGB', (100, 100), color='red')
            
            # Sauvegarder temporairement
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            img.save(temp_file.name, 'JPEG')
            
            return temp_file.name
            
        except ImportError:
            logger.error("PIL non disponible pour créer image de test")
            raise
        except Exception as e:
            logger.error(f"Erreur création image test: {e}")
            raise


# Exemple d'utilisation et tests
if __name__ == "__main__":
    import sys
    import logging
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
    
    print("🚀 Test AIService avec configuration externalisée")
    print("=" * 60)
    
    try:
        # Configuration de test pour GeoService
        from geo_service import GeoService
        
        db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': 'mysqlroot', 
            'database': 'immich_gallery',
            'charset': 'utf8mb4'
        }
        
        # Initialiser les services
        geo_service = GeoService(db_config)
        ai_service = AIService(geo_service)
        
        # Afficher la configuration
        print("📊 Configuration chargée:")
        config_summary = ai_service.config.export_config_summary()
        for key, value in config_summary.items():
            print(f"   {key}: {value}")
        
        # Options supportées
        print(f"\n🌐 Options supportées:")
        options = ai_service.get_supported_options()
        print(f"   Langues: {options['languages']}")
        print(f"   Styles: {options['styles']}")
        
        # Test du pipeline complet
        print(f"\n🧪 Test du pipeline complet...")
        test_result = ai_service.test_pipeline()
        
        print(f"📋 Résultats:")
        print(f"   Config valide: {'✅' if test_result['config_valid'] else '❌'}")
        if test_result['config_issues']:
            for issue in test_result['config_issues']:
                print(f"   ⚠️  {issue}")
        
        print(f"   Test réussi: {'✅' if test_result['test_successful'] else '❌'}")
        print(f"   Durée: {test_result['test_duration_seconds']:.1f}s")
        
        if test_result['result']:
            result = test_result['result']
            print(f"   Confiance: {result['confidence']:.2f}")
            print(f"   Légende: {result['caption'][:100]}...")
            print(f"   Modèles: {', '.join(result['models_used'])}")
        
        # Statistiques finales
        print(f"\n📊 Statistiques:")
        stats = ai_service.get_stats()
        print(f"   Requêtes totales: {stats['total_requests']}")
        print(f"   Taux de succès: {stats['success_rate']:.1f}%")
        print(f"   Temps moyen: {stats['average_processing_time']:.1f}s")
        
        print(f"\n🎉 AIService avec configuration externalisée prêt !")
        
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)