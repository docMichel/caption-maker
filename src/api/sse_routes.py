#!/usr/bin/env python3
"""
📍 src/api/sse_routes.py
Routes API pour Server-Sent Events (SSE) - VERSION SIMPLIFIÉE
"""

from flask import Blueprint, request, jsonify, Response, current_app
import logging
from typing import Dict, Any
import threading

# Import des handlers
from .sse_handlers import (
    StreamHandler,
    CaptionGenerationHandler,
    RegenerateHandler
)

logger = logging.getLogger(__name__)

# Créer le blueprint
sse_bp = Blueprint('sse', __name__)


@sse_bp.route('/ai/generate-caption-stream/<request_id>')
def generate_caption_stream(request_id: str):
    """Endpoint SSE pour stream de progression"""
    stream_handler = StreamHandler()
    return stream_handler.create_stream(request_id)


@sse_bp.route('/ai/generate-caption-async', methods=['POST'])
def generate_caption_async():
    """Endpoint pour démarrer une génération asynchrone"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'Corps JSON requis',
                'code': 'INVALID_JSON'
            }), 400
        
        request_id = data.get('request_id')
        if not request_id:
            return jsonify({
                'success': False,
                'error': 'request_id requis pour SSE',
                'code': 'MISSING_REQUEST_ID'
            }), 400
        
        # Valider les paramètres
        handler = CaptionGenerationHandler()
        validation_error = handler.validate_params(data)
        if validation_error:
            return validation_error
        
        # Récupérer l'app pour le contexte
        app = current_app._get_current_object()
        
        # Démarrer le traitement en arrière-plan
        thread = threading.Thread(
            target=handler.process_async,
            args=(request_id, data, app),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            'success': True,
            'request_id': request_id,
            'message': 'Génération démarrée, connectez-vous au flux SSE',
            'sse_url': f'/api/ai/generate-caption-stream/{request_id}'
        })
        
    except Exception as e:
        logger.error(f"❌ Erreur démarrage génération async: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'code': 'ASYNC_START_ERROR'
        }), 500


@sse_bp.route('/ai/regenerate-final', methods=['POST'])
def regenerate_final():
    """Régénérer uniquement la légende finale"""
    handler = RegenerateHandler()
    return handler.regenerate(request.get_json())