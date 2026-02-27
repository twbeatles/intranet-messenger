# -*- coding: utf-8 -*-
"""
Deprecated compatibility entrypoint.

This repository now uses `server.py` + `app/*` as the single source of truth.
`messenger_server.py` is kept only for backward compatibility with old launch
scripts and should not contain runtime logic.
"""

from __future__ import annotations

import sys
import warnings


def main(argv: list[str] | None = None):
    argv = list(sys.argv if argv is None else argv)
    warnings.warn(
        "messenger_server.py is deprecated; use `python server.py --cli`.",
        DeprecationWarning,
        stacklevel=2,
    )

    from server import run_server_cli, run_server_gui

    if len(argv) > 1 and argv[1] == "--cli":
        run_server_cli()
        return

    try:
        run_server_gui()
    except ImportError:
        run_server_cli()


if __name__ == "__main__":
    main()
