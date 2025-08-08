#!/usr/bin/env python3
"""
📍 src/utils/sse_manager.py

Gestionnaire centralisé pour les Server-Sent Events (SSE)
Gère les connexions, messages et broadcasting
"""

import json
import queue
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


class SSEConnection:
    """Représente une connexion SSE individuelle"""
    
    def __init__(self, request_id: str, timeout: float = 1.0):
        self.request_id = request_id
        self.message_queue = queue.Queue()
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
        except queue.Empty:
            return None
    
    def close(self):
        """Fermer la connexion"""
        self.is_active = False
        # Vider la queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except queue.Empty:
                break


class SSEManager:
    """Gestionnaire global des connexions SSE"""
    
    def __init__(self):
        self.connections: Dict[str, Queue] = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        self.debug_sse = True  # Flag pour activer/désactiver le debug
        
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
            # Tronquer les longues valeurs pour la lisibilité
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
    
    def send_event(self, connection_id: str, event_data: Dict[str, Any]) -> bool:
        """Envoyer un événement à une connexion spécifique"""
        with self.lock:
            if connection_id in self.connections:
                try:
                    # Logger avant envoi
                    event_type = event_data.get('event', 'message')
                    self._debug_log_event(connection_id, event_type, event_data.get('data'))
                    
                    self.connections[connection_id].put(event_data)
                    return True
                except Exception as e:
                    self.logger.error(f"❌ Erreur envoi SSE [{connection_id}]: {e}")
                    return False
            else:
                self.logger.warning(f"⚠️ Connexion SSE non trouvée: {connection_id}")
                return False
    

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
        return self.connections.get(request_id)
    
    def close_connection(self, request_id: str):
        """Fermer et supprimer une connexion"""
        with self.lock:
            if request_id in self.connections:
                self.connections[request_id].close()
                del self.connections[request_id]
                self.stats['active_connections'] = len(self.connections)
                logger.info(f"📡 Connexion SSE fermée: {request_id}")
    
  
    
    def _send_message(self, request_id: str, event: str, data: Dict[str, Any]):
        """Méthode interne pour envoyer un message"""
        connection = self.get_connection(request_id)
        if connection:
            try:
                connection.send_message(event, data)
                self.stats['messages_sent'] += 1
                logger.debug(f"📨 Message SSE envoyé: {event} → {request_id}")
            except Exception as e:
                logger.error(f"❌ Erreur envoi SSE: {e}")
                self.stats['errors'] += 1
        else:
            logger.warning(f"⚠️ Connexion SSE non trouvée: {request_id}")
    
    
    def broadcast_progress(self, connection_id: str, step: str, progress: int, message: str):
        """Envoyer une mise à jour de progression"""
        event_data = {
            'event': 'progress',
            'data': {
                'step': step,
                'progress': progress,
                'message': message,
                'timestamp': datetime.now().isoformat()
            }
        }
        return self.send_event(connection_id, event_data)
    
    def broadcast_result(self, connection_id: str, step: str, result: Dict[str, Any]):
        """Envoyer un résultat intermédiaire"""
        event_data = {
            'event': 'result',
            'data': {
                'step': step,
                'result': result,
                'timestamp': datetime.now().isoformat()
            }
        }
        return self.send_event(connection_id, event_data)
    
    def broadcast_complete(self, connection_id: str, data: Dict[str, Any]):
        """Envoyer le résultat final"""
        event_data = {
            'event': 'complete',
            'data': data
        }
        return self.send_event(connection_id, event_data)
    
    def broadcast_error(self, connection_id: str, error: str, error_type: str = "ERROR"):
        """Envoyer une erreur"""
        event_data = {
            'event': 'error',
            'data': {
                'error': error,
                'error_type': error_type,
                'timestamp': datetime.now().isoformat()
            }
        }
        return self.send_event(connection_id, event_data)

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
        """Formater un message pour SSE"""
        event_type = message.get('event', 'message')
        data = json.dumps(message)
        
        # Format SSE standard
        lines = []
        lines.append(f"event: {event_type}")
        lines.append(f"data: {data}")
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