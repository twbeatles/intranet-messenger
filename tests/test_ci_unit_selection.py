# -*- coding: utf-8 -*-
"""CI selection guard: unit job must never break on env-only dependencies.

Regression tests for the `unit` job failures:

- 2026-10-15/22: `pytest tests` collected `tests/test_browser_e2e.py`,
  whose top-level `import requests` raised `ModuleNotFoundError` because
  E2E-only deps (requests / python-socketio / playwright + Chromium) are
  installed in the `network-e2e` job, not in `requirements.txt`. The whole
  unit run aborted at collection.
- 2026-10-22: `tests/test_gui_import_smoke.py` raised
  `ImportError: libEGL.so.1` because PySide6 wheels link against system
  GL/EGL libs missing from the minimal `ubuntu-latest` image.

Two-layer defense per case, both pinned here:
1. The test module itself must degrade to skip when its env-only
   dependency is missing (importorskip / guarded import), never raise.
2. `.github/workflows/quality.yml` `unit` must either provide that
   dependency (apt Qt runtime libs / network-e2e installs) or exclude the
   module (explicit --ignore and/or `-m "not browser"`).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "quality.yml"
BROWSER_E2E = REPO_ROOT / "tests" / "test_browser_e2e.py"
GUI_SMOKE = REPO_ROOT / "tests" / "test_gui_import_smoke.py"


def _unit_section() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    # Lines/steps of the unit job: from "jobs:" up to the "network-e2e:"
    # job header.
    return text.split("network-e2e:")[0]


def _unit_pytest_invocations() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    # Lines invoking pytest that belong to the unit job: from "jobs:" up to
    # the "network-e2e:" job header, containing "pytest".
    unit_section = text.split("network-e2e:")[0]
    return [ln.strip() for ln in unit_section.splitlines() if "pytest" in ln]


def test_unit_job_excludes_browser_e2e():
    invocations = _unit_pytest_invocations()
    assert invocations, "unit job must invoke pytest"
    joined = "\n".join(invocations)
    excluded = (
        "test_browser_e2e" in joined  # explicit --ignore of the module
        or re.search(r'-m\s+["\']?not browser', joined) is not None
    )
    assert excluded, (
        "unit pytest selection must exclude tests/test_browser_e2e.py "
        f"(explicit --ignore or -m 'not browser'); got: {invocations}"
    )


def test_browser_e2e_degrades_without_e2e_deps():
    source = BROWSER_E2E.read_text(encoding="utf-8")
    hard_import = re.search(r"^import requests\s*$", source, re.MULTILINE)
    guarded = (
        "importorskip" in source
        or re.search(r"try:\s*\n\s*import requests", source) is not None
    )
    assert not hard_import or guarded, (
        "tests/test_browser_e2e.py must not hard-require `requests` at "
        "module import (use pytest.importorskip or try/except) so unit "
        "collection skips instead of raising ModuleNotFoundError"
    )


def test_gui_smoke_degrades_without_qt_native_libs():
    source = GUI_SMOKE.read_text(encoding="utf-8")
    guarded = "pytest.skip" in source and "except ImportError" in source
    assert guarded, (
        "tests/test_gui_import_smoke.py must degrade to pytest.skip on "
        "ImportError (missing system EGL/GL libs on minimal images) "
        "instead of failing the unit run"
    )


def test_unit_job_provides_qt_runtime_or_excludes_gui_smoke():
    unit_section = _unit_section().lower()
    provides_libs = "libegl" in unit_section  # apt Qt runtime libs
    excludes_gui = "test_gui_import_smoke" in unit_section
    assert provides_libs or excludes_gui, (
        "unit job must install Qt runtime libs (apt libegl1 ...) so "
        "PySide6 imports resolve, or explicitly exclude "
        "tests/test_gui_import_smoke.py from its pytest selection"
    )
