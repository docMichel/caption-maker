#!/usr/bin/env python3
"""
📍 src/utils/sse_manager.py

Gestionnaire centralisé pour les Server-Sent Events (SSE)
Gère les connexions, messages et broadcasting
"""

import json
import queue
from queue import Queue, Empty
import logging
import threading
import time
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SSEConnection:
    """Représente une connexion SSE individuelle"""
    
    def __init__(self, request_id: str, timeout: float = 1.0):
        self.request_id = request_id
        self.message_queue = Queue()
        self.timeout = timeout
        self.created_at = time.time()
        self.last_activity = time.time()
        self.is_active = True
    
    def send_message(self, event: str, data: Dict[str, Any]):
        """Ajouter un message à la queue"""
        if self.is_active:
            message = {
                'event': event,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }
            self.message_queue.put(message)
            self.last_activity = time.time()
    
    def get_message(self, timeout: Optional[float] = None) -> Optional[Dict]:
        """Récupérer un message de la queue"""
        try:
            return self.message_queue.get(timeout=timeout or self.timeout)
        except Empty:
            return None
    
    def close(self):
        """Fermer la connexion"""
        self.is_active = False
        # Vider la queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except Empty:
                break


class SSEManager:
    """Gestionnaire global des connexions SSE"""
    
    def __init__(self):
        # Stockage des connexions SSEConnection
        self.connections: Dict[str, SSEConnection] = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        self.debug_sse = True
        
        self.stats = {
            'total_connections': 0,
            'active_connections': 0,
            'messages_sent': 0,
            'errors': 0
        }
    
    def _debug_log_event(self, connection_id: str, event_type: str, data: Any):
        """Logger les événements SSE pour debug (sauf heartbeat)"""
        if not self.debug_sse or event_type == 'heartbeat':
            return
            
        # Formater le message pour le debug
        if isinstance(data, dict):
            debug_data = {}
            for k, v in data.items():
                if isinstance(v, str) and len(v) > 100:
                    debug_data[k] = f"{v[:100]}..."
                elif isinstance(v, dict):
                    debug_data[k] = f"<dict with {len(v)} keys>"
                elif isinstance(v, list):
                    debug_data[k] = f"<list with {len(v)} items>"
                else:
                    debug_data[k] = v
        else:
            debug_data = data
            
        self.logger.info(f"📤 SSE [{connection_id}] event='{event_type}' data={debug_data}")
    
    def create_connection(self, request_id: str, timeout: float = 1.0) -> SSEConnection:
        """Créer une nouvelle connexion SSE"""
        with self.lock:
            # Fermer une connexion existante si elle existe
            if request_id in self.connections:
                self.close_connection(request_id)
            
            # Créer la nouvelle connexion
            connection = SSEConnection(request_id, timeout)
            self.connections[request_id] = connection
            
            self.stats['total_connections'] += 1
            self.stats['active_connections'] = len(self.connections)
            
            logger.info(f"📡 Connexion SSE créée: {request_id}")
            return connection
    
    def get_connection(self, request_id: str) -> Optional[SSEConnection]:
        """Récupérer une connexion existante"""
        with self.lock:
            return self.connections.get(request_id)
    
    def close_connection(self, request_id: str):
        """Fermer et supprimer une connexion"""
        with self.lock:
            if request_id in self.connections:
                self.connections[request_id].close()
                del self.connections[request_id]
                self.stats['active_connections'] = len(self.connections)
                logger.info(f"📡 Connexion SSE fermée: {request_id}")
    
    def send_event(self, connection_id: str, event_data: Dict[str, Any]) -> bool:
        """
        Envoyer un événement à une connexion spécifique
        
        Format attendu de event_data:
        {
            'event': 'progress',  # Type d'événement
            'data': {...}         # Données de l'événement
        }
        """
        with self.lock:
            connection = self.connections.get(connection_id)
            if connection:
                try:
                    event_type = event_data.get('event', 'message')
                    data = event_data.get('data', {})
                    
                    # Debug log
                    self._debug_log_event(connection_id, event_type, data)
                    
                    # Envoyer via SSEConnection
                    connection.send_message(event_type, data)
                    self.stats['messages_sent'] += 1
                    return True
                    
                except Exception as e:
                    self.logger.error(f"❌ Erreur envoi SSE [{connection_id}]: {e}")
                    self.stats['errors'] += 1
                    return False
            else:
                self.logger.warning(f"⚠️ Connexion SSE non trouvée: {connection_id}")
                return False
    
    def broadcast_progress(self, connection_id: str, step: str, progress: int, message: str):
        """Envoyer une mise à jour de progression"""
        return self.send_event(connection_id, {
            'event': 'progress',
            'data': {
                'step': step,
                'progress': progress,
                'message': message
            }
        })
    
    def broadcast_result(self, connection_id: str, step: str, result: Dict[str, Any]):
        """Envoyer un résultat intermédiaire"""
        return self.send_event(connection_id, {
            'event': 'result',
            'data': {
                'step': step,
                'result': result
            }
        })
    
    def broadcast_complete(self, connection_id: str, data: Dict[str, Any]):
        """
        Envoyer le résultat final
        
        IMPORTANT: 'data' contient déjà toutes les données finales,
        pas besoin de double-wrapper
        """
        return self.send_event(connection_id, {
            'event': 'complete',
            'data': data  # Pas de double wrapping !
        })
    
    def broadcast_error(self, connection_id: str, error: str, error_type: str = "ERROR"):
        """Envoyer une erreur"""
        return self.send_event(connection_id, {
            'event': 'error',
            'data': {
                'error': error,
                'error_type': error_type
            }
        })
    
    def broadcast_warning(self, connection_id: str, message: str):
        """Envoyer un avertissement"""
        return self.send_event(connection_id, {
            'event': 'warning',
            'data': {
                'message': message
            }
        })
    
    def cleanup_inactive_connections(self, max_inactive_seconds: int = 300):
        """Nettoyer les connexions inactives"""
        with self.lock:
            current_time = time.time()
            to_remove = []
            
            for request_id, connection in self.connections.items():
                inactive_time = current_time - connection.last_activity
                if inactive_time > max_inactive_seconds:
                    to_remove.append(request_id)
            
            for request_id in to_remove:
                self.close_connection(request_id)
                logger.info(f"🗑️ Connexion SSE inactive supprimée: {request_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Récupérer les statistiques"""
        with self.lock:
            return {
                **self.stats,
                'connections_details': {
                    request_id: {
                        'created_at': datetime.fromtimestamp(conn.created_at).isoformat(),
                        'last_activity': datetime.fromtimestamp(conn.last_activity).isoformat(),
                        'queue_size': conn.message_queue.qsize(),
                        'is_active': conn.is_active
                    }
                    for request_id, conn in self.connections.items()
                }
            }
    
    def format_sse_response(self, message: Dict[str, Any]) -> str:
        """
        Formater un message pour SSE
        
        Format SSE standard:
        event: <type>
        data: <json>
        
        """
        event_type = message.get('event', 'message')
        data = message.get('data', {})
        
        # Format SSE standard
        lines = []
        lines.append(f"event: {event_type}")
        lines.append(f"data: {json.dumps(data)}")
        lines.append("")  # Ligne vide pour séparer les messages
        
        return "\n".join(lines) + "\n"


# Instance globale
_sse_manager = None

def get_sse_manager() -> SSEManager:
    """Obtenir l'instance globale du gestionnaire SSE"""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager