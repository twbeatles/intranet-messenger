# -*- coding: utf-8 -*-
"""
HTTP blueprint registration.
"""

from __future__ import annotations

from app.http.auth import auth_bp
from app.http.public import public_bp
from app.http.rooms import rooms_bp


def register_routes(app):
    from app.http.collaboration import collaboration_bp
    from app.http.messages import messages_bp
    from app.http.profile import profile_bp
    from app.http.uploads import uploads_bp

    for blueprint in (
        public_bp,
        auth_bp,
        rooms_bp,
        messages_bp,
        uploads_bp,
        profile_bp,
        collaboration_bp,
    ):
        app.register_blueprint(blueprint)
