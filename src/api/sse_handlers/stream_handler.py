#!/usr/bin/env python3
"""Handler pour le streaming SSE"""

from flask import Response
import json
import time
import logging
from utils.sse_manager import get_sse_manager

logger = logging.getLogger(__name__)


class StreamHandler:
    """Gestion du stream SSE"""
    
    def create_stream(self, request_id: str) -> Response:
        """Créer un stream SSE pour un request_id"""
        
        def event_stream():
            """Générateur de flux SSE"""
            sse_manager = get_sse_manager()
            connection = sse_manager.create_connection(request_id)
            
            try:
                # Envoyer l'événement connected selon le format
                connected_event = sse_manager.format_sse_response({
                    'event': 'connected',
                    'data': {
                        'message': 'Connexion SSE établie',
                        'request_id': request_id,
                        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z')
                    }
                })
                yield connected_event
                
                # Boucle de lecture des messages
                heartbeat_count = 0
                while connection.is_active:
                    # Récupérer un message
                    message = connection.get_message(timeout=1.0)
                    
                    if message:
                        # Formater et envoyer le message SSE
                        sse_response = sse_manager.format_sse_response(message)
                        yield sse_response
                        
                        # Si c'est un message de fin, arrêter le flux
                        if message.get('event') in ['complete', 'error']:
                            break
                    else:
                        # Heartbeat toutes les 30 secondes
                        heartbeat_count += 1
                        if heartbeat_count >= 30:
                            heartbeat = {
                                'event': 'heartbeat',
                                'data': {
                                    'timestamp': int(time.time() * 1000)
                                }
                            }
                            yield sse_manager.format_sse_response(heartbeat)
                            heartbeat_count = 0
                            
            except GeneratorExit:
                logger.info(f"Client déconnecté: {request_id}")
            finally:
                sse_manager.close_connection(request_id)
        
        return Response(
            event_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Cache-Control',
                'X-Accel-Buffering': 'no'
            }
        )