# -*- coding: utf-8 -*-
"""
Compatibility shim for HTTP route registration.

Tests and older code paths still patch symbols on this module, so it continues
to re-export selected dependencies while delegating route registration to the
split blueprint package.
"""

from __future__ import annotations

from app.http import register_routes
from app.models import advanced_search
from app.upload_scan import create_scan_job, get_scan_job, is_scan_enabled

__all__ = [
    "register_routes",
    "advanced_search",
    "create_scan_job",
    "get_scan_job",
    "is_scan_enabled",
]
