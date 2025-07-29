#!/usr/bin/env python3
"""
📍 src/api/__init__.py

Module API - Organisation des routes Flask
"""

from .routes import api_bp
from .sse_routes import sse_bp
from .admin_routes import admin_bp

__all__ = ['api_bp', 'sse_bp', 'admin_bp']