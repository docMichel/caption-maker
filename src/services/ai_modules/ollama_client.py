#!/usr/bin/env python3
#services/ai_modules/ollama_client.py
"""Client Ollama partagé pour tous les modules"""

import requests
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class OllamaClient:
    """Client réutilisable pour Ollama"""
    
    def __init__(self, base_url: str, timeout: int = 30, max_retries: int = 3):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        
    def call_with_retry(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Appel Ollama avec retry automatique"""
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.base_url}/api/{endpoint}",
                    json=payload,
                    timeout=min(self.timeout, 30)
                )
                response.raise_for_status()
                return response.json()
                
            except requests.Timeout:
                logger.warning(f"⏱️ Timeout tentative {attempt + 1}/{self.max_retries}")
                if attempt == self.max_retries - 1:
                    raise TimeoutError("Ollama timeout")
                time.sleep(2)
                
            except Exception as e:
                logger.warning(f"Erreur tentative {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    return None
                time.sleep(1)
        
        return None
    
    def generate_text(self, model: str, prompt: str, temperature: float = 0.7, 
                     max_tokens: int = 150) -> Optional[str]:
        """Génération de texte simple"""
        payload = {
            'model': model,
            'prompt': prompt,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens
            }
        }
        
        response = self.call_with_retry('generate', payload)
        return response.get('response', '').strip() if response else None