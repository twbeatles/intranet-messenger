# -*- coding: utf-8 -*-
"""
Upload path helpers used by HTTP routes and AV scan worker flows.
"""

from __future__ import annotations

import os


def normalize_stored_path(root_path: str, target_path: str) -> str:
    """Return a stable stored path for DB/job state.

    Prefer relative paths under ``root_path`` so existing behavior stays compact.
    If the target is outside the root or on another Windows drive, keep the
    absolute path instead of raising ``ValueError``.
    """

    root_abs = os.path.abspath(root_path)
    target_abs = os.path.abspath(target_path)

    try:
        common_root = os.path.commonpath([root_abs, target_abs])
    except ValueError:
        return target_abs

    if common_root != root_abs:
        return target_abs

    try:
        return os.path.relpath(target_abs, root_abs).replace("\\", "/")
    except ValueError:
        return target_abs


def resolve_stored_path(root_path: str, stored_path: str) -> str:
    """Resolve a stored upload path back to an absolute path."""

    if os.path.isabs(stored_path):
        return stored_path
    return os.path.join(root_path, stored_path)
