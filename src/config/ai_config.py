#!/usr/bin/env python3
"""
📍 src/config/ai_config.py

Configuration loader pour AIService
Charge les prompts et templates depuis YAML
Permet modification à chaud sans recompilation
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import re

logger = logging.getLogger(__name__)

class AIConfig:
    """Gestionnaire de configuration pour l'AIService"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialiser le gestionnaire de config
        
        Args:
            config_path: Chemin vers le fichier YAML (défaut: ai_prompts.yaml)
        """
        if config_path is None:
            # Chemin par défaut relatif à ce fichier
            config_path = Path(__file__).parent / "ai_prompts.yaml"
        
        self.config_path = Path(config_path)
        self._config = {}
        self._load_config()
    
    def _load_config(self):
        """Charger la configuration depuis le fichier YAML"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            
            logger.info(f"✅ Configuration chargée depuis {self.config_path}")
            
        except FileNotFoundError:
            logger.error(f"❌ Fichier de config non trouvé: {self.config_path}")
            self._config = self._get_default_config()
            
        except yaml.YAMLError as e:
            logger.error(f"❌ Erreur parsing YAML: {e}")
            self._config = self._get_default_config()
        
        except Exception as e:
            logger.error(f"❌ Erreur chargement config: {e}")
            self._config = self._get_default_config()
    
    def reload_config(self):
        """Recharger la configuration depuis le fichier"""
        logger.info("🔄 Rechargement de la configuration...")
        self._load_config()
    
    # =================================================================
    # GETTERS POUR MODÈLES ET OLLAMA
    # =================================================================
    
    def get_models(self) -> Dict[str, str]:
        """Récupérer la configuration des modèles"""
        return self._config.get('models', {
            'vision': 'llava:7b',
            'caption': 'mistral:7b-instruct',
            'geo_enrichment': 'qwen2:7b'
        })
    
    def get_ollama_config(self) -> Dict[str, Any]:
        """Récupérer la configuration Ollama"""
        return self._config.get('ollama', {
            'base_url': 'http://localhost:11434',
            'timeout': 60,
            'default_temperature': 0.7,
            'max_retries': 3
        })
    
    # =================================================================
    # GETTERS POUR PROMPTS
    # =================================================================
    
    def get_image_analysis_prompt(self, detailed: bool = False) -> str:
        """Récupérer le prompt d'analyse d'image"""
        image_config = self._config.get('image_analysis', {})
        
        if detailed:
            return image_config.get('detailed_prompt', image_config.get('main_prompt', ''))
        else:
            return image_config.get('main_prompt', 'Décris cette image.')
    
    def get_image_analysis_params(self) -> Dict[str, Any]:
        """Récupérer les paramètres pour l'analyse d'image"""
        return self._config.get('image_analysis', {}).get('parameters', {
            'temperature': 0.6,
            'max_tokens': 200,
            'top_p': 0.9
        })
    
    def get_caption_prompt(self, language: str, style: str = 'creative') -> str:
        """
        Récupérer le template de légende
        
        Args:
            language: Code langue ('fr', 'en', 'bilingual')
            style: Style de légende ('creative', 'descriptive', 'minimal')
        """
        # Normaliser la langue
        lang_code = self._normalize_language(language)
        
        # Chercher le template approprié
        if lang_code == 'bilingual':
            templates = self._config.get('captions_bilingual', {})
        elif lang_code == 'en':
            templates = self._config.get('captions_english', {})
        else:  # défaut français
            templates = self._config.get('captions_french', {})
        
        # Récupérer le style demandé (défaut creative)
        return templates.get(style, templates.get('creative', 'Écris une légende pour cette photo.'))
    
    def get_cultural_enrichment_prompt(self, short: bool = False) -> str:
        """Récupérer le prompt d'enrichissement culturel"""
        cultural_config = self._config.get('cultural_enrichment', {})
        
        if short:
            return cultural_config.get('short_prompt', cultural_config.get('main_prompt', ''))
        else:
            return cultural_config.get('main_prompt', 'Enrichis ce contexte géographique.')
    
    def get_cultural_enrichment_params(self) -> Dict[str, Any]:
        """Récupérer les paramètres pour l'enrichissement culturel"""
        return self._config.get('cultural_enrichment', {}).get('parameters', {
            'temperature': 0.5,
            'max_tokens': 120,
            'top_p': 0.8
        })
    
    def get_hashtag_prompt(self) -> str:
        """Récupérer le prompt pour génération de hashtags"""
        return self._config.get('hashtags_generation', {}).get('prompt', '')
    
    def get_hashtag_params(self) -> Dict[str, Any]:
        """Récupérer les paramètres pour hashtags"""
        return self._config.get('hashtags_generation', {}).get('parameters', {
            'temperature': 0.6,
            'max_tokens': 50
        })

    
    # =================================================================
    # UTILITAIRES LANGUE ET STYLE
    # =================================================================
    
    def _normalize_language(self, language: str) -> str:
        """Normaliser le code langue"""
        language = language.lower().strip()
        
        supported_langs = self._config.get('supported_languages', [])
        
        for lang_config in supported_langs:
            if language in lang_config.get('names', []):
                return lang_config.get('code', 'fr')
        
        # Défaut français
        return 'fr'
    
    def get_supported_languages(self) -> List[Dict[str, Any]]:
        """Récupérer la liste des langues supportées"""
        return self._config.get('supported_languages', [
            {'code': 'fr', 'names': ['français', 'fr'], 'template_key': 'captions_french'},
            {'code': 'en', 'names': ['english', 'en'], 'template_key': 'captions_english'},
            {'code': 'bilingual', 'names': ['bilingual', 'bilingue'], 'template_key': 'captions_bilingual'}
        ])
    
    def get_supported_styles(self) -> List[Dict[str, Any]]:
        """Récupérer la liste des styles supportés"""
        return self._config.get('supported_styles', [
            {'name': 'creative', 'description': 'Poétique et évocateur', 'default': True},
            {'name': 'descriptive', 'description': 'Informatif et engageant'},
            {'name': 'minimal', 'description': 'Court et percutant'}
        ])
    
    def is_valid_language(self, language: str) -> bool:
        """Vérifier si une langue est supportée"""
        normalized = self._normalize_language(language)
        return normalized in [lang['code'] for lang in self.get_supported_languages()]
    
    def is_valid_style(self, style: str) -> bool:
        """Vérifier si un style est supporté"""
        styles = [s['name'] for s in self.get_supported_styles()]
        return style.lower() in styles
    
    # =================================================================
    # POST-PROCESSING ET FALLBACKS
    # =================================================================
    
    def get_post_processing_config(self) -> Dict[str, Any]:
        """Récupérer la configuration de post-processing"""
        return self._config.get('post_processing', {
            'max_caption_length': 500,
            'min_caption_length': 20,
            'max_sentences_if_too_long': 3,
            'remove_patterns': ["^#.*$", "\\*{2,}", "_{2,}"],
            'forbidden_words': []
        })
    
    def get_fallback_message(self, language: str, message_type: str) -> str:
        """
        Récupérer un message de fallback
        
        Args:
            language: Code langue
            message_type: Type de message ('no_image', 'no_location', 'generic_error')
        """
        lang_code = self._normalize_language(language)
        
        fallbacks = self._config.get('fallback_messages', {})
        lang_fallbacks = fallbacks.get('french' if lang_code == 'fr' else 'english', {})
        
        return lang_fallbacks.get(message_type, 'Une belle photo capturée dans un moment unique.')
    
    def get_quality_scoring_config(self) -> Dict[str, Any]:
        """Récupérer la configuration du scoring de qualité"""
        return self._config.get('quality_scoring', {
            'weights': {
                'image_analysis': 0.3,
                'geo_context': 0.4,
                'caption_quality': 0.3
            },
            'caption_quality_factors': {
                'min_words': 10,
                'max_words': 150,
                'ideal_words_min': 40,
                'ideal_words_max': 120
            }
        })
    
    # =================================================================
    # POST-PROCESSING HELPERS
    # =================================================================
    
    def clean_caption(self, caption: str) -> str:
        """Nettoyer une légende selon la configuration"""
        if not caption:
            return caption
        
        post_config = self.get_post_processing_config()
        
        # Supprimer les patterns indésirables
        for pattern in post_config.get('remove_patterns', []):
            caption = re.sub(pattern, '', caption, flags=re.MULTILINE)
        
        # Supprimer les mots interdits
        for word in post_config.get('forbidden_words', []):
            caption = re.sub(re.escape(word), '', caption, flags=re.IGNORECASE)
        
        # Nettoyer les espaces
        caption = re.sub(r'\s+', ' ', caption).strip()
        
        # Limiter la longueur
        max_length = post_config.get('max_caption_length', 500)
        if len(caption) > max_length:
            sentences = caption.split('.')
            max_sentences = post_config.get('max_sentences_if_too_long', 3)
            caption = '. '.join(sentences[:max_sentences]) + '.'
        
        return caption
    
    def calculate_caption_quality_score(self, caption: str) -> float:
        """Calculer un score de qualité pour une légende"""
        if not caption:
            return 0.0
        
        quality_config = self.get_quality_scoring_config()
        factors = quality_config.get('caption_quality_factors', {})
        
        words = len(caption.split())
        score = 0.5  # Score de base
        
        # Score basé sur la longueur
        min_words = factors.get('min_words', 10)
        max_words = factors.get('max_words', 150)
        ideal_min = factors.get('ideal_words_min', 40)
        ideal_max = factors.get('ideal_words_max', 120)
        
        if words < min_words:
            score -= 0.3
        elif words > max_words:
            score -= 0.2
        elif ideal_min <= words <= ideal_max:
            score += 0.3
        else:
            score += 0.1
        
        # Bonus/Malus basés sur le contenu
        if '#' in caption:
            score += factors.get('penalty_hashtags', -0.2)
        
        # Chercher des métaphores/richesse (approximatif)
        metaphor_words = ['comme', 'tel', 'ainsi', 'pareil', '似', 'like', 'as if']
        if any(word in caption.lower() for word in metaphor_words):
            score += factors.get('bonus_for_metaphors', 0.1)
        
        return max(0.0, min(1.0, score))
    
    # =================================================================
    # DEBUG ET UTILITAIRES
    # =================================================================
    
    def get_debug_config(self) -> Dict[str, bool]:
        """Récupérer la configuration de debug"""
        return self._config.get('debug', {
            'log_prompts': False,
            'log_responses': False,
            'save_failed_generations': True,
            'detailed_timing': False
        })
    
    def export_config_summary(self) -> Dict[str, Any]:
        """Exporter un résumé de la configuration pour debug"""
        return {
            'config_path': str(self.config_path),
            'models': self.get_models(),
            'supported_languages': [lang['code'] for lang in self.get_supported_languages()],
            'supported_styles': [style['name'] for style in self.get_supported_styles()],
            'ollama_url': self.get_ollama_config().get('base_url'),
            'debug_enabled': any(self.get_debug_config().values())
        }
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Configuration par défaut si le fichier YAML est inaccessible"""
        return {
            'models': {
                'vision': 'llava:7b',
                'caption': 'mistral:7b-instruct',
                'geo_enrichment': 'qwen2:7b'
            },
            'ollama': {
                'base_url': 'http://localhost:11434',
                'timeout': 60,
                'default_temperature': 0.7
            },
            'captions_french': {
                'creative': 'Écris une légende Instagram créative en français pour cette photo avec {image_description}. Lieu: {location_basic}. Style poétique, 80-120 mots, pas de hashtags.'
            },
            'captions_english': {
                'creative': 'Write a creative Instagram caption in English for this photo with {image_description}. Location: {location_basic}. Poetic style, 80-120 words, no hashtags.'
            }
        }


# Exemple d'utilisation
if __name__ == "__main__":
    # Test du gestionnaire de config
    print("🧪 Test AIConfig")
    print("=" * 40)
    
    try:
        config = AIConfig()
        
        print("📊 Résumé configuration:")
        summary = config.export_config_summary()
        for key, value in summary.items():
            print(f"  {key}: {value}")
        
        print(f"\n🤖 Modèles configurés:")
        models = config.get_models()
        for role, model in models.items():
            print(f"  {role}: {model}")
        
        print(f"\n🌍 Langues supportées:")
        for lang in config.get_supported_languages():
            print(f"  {lang['code']}: {', '.join(lang['names'])}")
        
        print(f"\n🎨 Styles supportés:")
        for style in config.get_supported_styles():
            print(f"  {style['name']}: {style['description']}")
        
        print(f"\n📝 Test prompt français créatif:")
        prompt = config.get_caption_prompt('français', 'creative')
        print(f"  Longueur: {len(prompt)} caractères")
        print(f"  Début: {prompt[:100]}...")
        
        print(f"\n🧹 Test nettoyage légende:")
        test_caption = "Belle photo! #travel #amazing *** Check link in bio ***"
        cleaned = config.clean_caption(test_caption)
        print(f"  Avant: {test_caption}")
        print(f"  Après: {cleaned}")
        
        print(f"\n✅ AIConfig fonctionne parfaitement!")
        
    except Exception as e:
        print(f"❌ Erreur test AIConfig: {e}")