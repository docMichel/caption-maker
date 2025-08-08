#!/usr/bin/env python3
"""Handler pour la régénération de légendes"""

from flask import jsonify, current_app
import logging
import time

logger = logging.getLogger(__name__)


class RegenerateHandler:
    """Gestion de la régénération de légendes"""
    
    def regenerate(self, data: dict):
        """Régénérer une légende à partir des contextes modifiés"""
        try:
            if not data:
                return jsonify({
                    'success': False,
                    'error': 'Corps JSON requis'
                }), 400
            
            # Extraire les paramètres
            image_description = data.get('image_description', '')
            geo_context = data.get('geo_context', '')
            cultural_enrichment = data.get('cultural_enrichment', '')
            travel_enrichment = data.get('travel_enrichment', '')
            language = data.get('language', 'français')
            style = data.get('style', 'creative')
            
            logger.info("♻️ Régénération légende finale")
            
            # Récupérer le service IA
            ai_service = current_app.config.get('SERVICES', {}).get('ai_service')
            
            if not ai_service:
                return jsonify({
                    'success': False,
                    'error': 'Service IA non disponible'
                }), 503
            
            # Utiliser directement le caption_generator du service
            caption_generator = ai_service.caption_generator
            
            # Préparer le contexte complet
            context = {
                'image_description': image_description,
                'location_basic': geo_context,
                'cultural_context': geo_context,
                'cultural_enrichment': cultural_enrichment,
                'travel_enrichment': travel_enrichment or '',
                'nearby_attractions': '',
                'geographic_context': ''
            }
            
            # S'assurer qu'aucune valeur n'est None
            context = {k: v or '' for k, v in context.items()}
            
            # Générer avec le module caption_generator
            # Note: On utilise la version synchrone ici
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                raw_caption = loop.run_until_complete(
                    caption_generator.generate(context, language, style)
                )
            finally:
                loop.close()
            
            # Post-traitement avec la config
            final_caption = ai_service.config.clean_caption(raw_caption)
            
            logger.info("✅ Légende finale régénérée")
            
            return jsonify({
                'success': True,
                'caption': final_caption,
                'raw_caption': raw_caption,
                'confidence_score': 0.8,
                'language': language,
                'style': style,
                'generation_time': 0.1,
                'method': 'regenerated',
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except Exception as e:
            logger.error(f"❌ Erreur régénération: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': str(e),
                'code': 'REGENERATION_ERROR'
            }), 500