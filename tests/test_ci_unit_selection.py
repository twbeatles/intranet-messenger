# -*- coding: utf-8 -*-
"""CI selection guard: unit job must never collect E2E-only modules.

Regression test for the 2026-10-15/22 `unit` job failures: `pytest tests`
collected `tests/test_browser_e2e.py`, whose top-level `import requests`
raised `ModuleNotFoundError` because E2E-only deps (requests /
python-socketio / playwright + Chromium) are installed in the `network-e2e`
job, not in `requirements.txt`. The whole unit run aborted at collection.

Two-layer defense, both pinned here:
1. `tests/test_browser_e2e.py` must degrade to skip-at-collection when
   E2E-only deps are missing (importorskip / guarded import), never raise.
2. `.github/workflows/quality.yml` `unit` selection must exclude the
   browser E2E module (explicit --ignore and/or `-m "not browser"`).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "quality.yml"
BROWSER_E2E = REPO_ROOT / "tests" / "test_browser_e2e.py"


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
