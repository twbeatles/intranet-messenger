# -*- coding: utf-8 -*-
"""
Socket event package.
"""


def register_socket_events(socketio):
    from app.socket_events.register import register_socket_events as _register_socket_events

    return _register_socket_events(socketio)


__all__ = ["register_socket_events"]
