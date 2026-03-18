# -*- coding: utf-8 -*-
"""
Socket.IO event registration entrypoint.
"""

from __future__ import annotations

from app.socket_events.connection import register_connection_events
from app.socket_events.features import register_feature_events
from app.socket_events.messages import register_message_events
from app.socket_events.presence import register_presence_events
from app.socket_events.rooms import register_room_events


def register_socket_events(socketio):
    register_connection_events(socketio)
    register_message_events(socketio)
    register_presence_events(socketio)
    register_room_events(socketio)
    register_feature_events(socketio)

