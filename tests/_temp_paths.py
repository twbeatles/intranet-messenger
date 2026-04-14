from __future__ import annotations

from pathlib import Path
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
TMP_ROOT = REPO_ROOT / ".pytest_tmp"


def ensure_temp_root() -> str:
    TMP_ROOT.mkdir(exist_ok=True)
    return str(TMP_ROOT)


def make_temp_dir(*, prefix: str = "tmp-") -> str:
    return tempfile.mkdtemp(prefix=prefix, dir=ensure_temp_root())


def make_temp_file(*, prefix: str = "tmp-", suffix: str = "") -> tuple[int, str]:
    return tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=ensure_temp_root())
