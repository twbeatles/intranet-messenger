from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
UTF8_BOM = b"\xef\xbb\xbf"
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".ini",
    ".cfg",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".js",
    ".css",
    ".html",
    ".svg",
    ".ps1",
    ".bat",
    ".sh",
}
TEXT_FILENAMES = {"Dockerfile", "Makefile", "pytest.ini"}
MINIFIED_SKIP_SUFFIXES = (".min.js",)
MOJIBAKE_ALLOWLIST = {"app/__init__.py", "app/sockets.py", "tests/test_encoding_hygiene.py"}
MOJIBAKE_HINTS = (
    "嚥≪뮄",
    "袁⑹뒄",
    "類ㅼ삢",
    "癒?퐣",
    "猷?",
    "紐꾩뵠",
    "?몃빍",
    "揶쏅벤",
    "?밴쉐",
    "?⑤벊",
    "??뵬",
    "筌뤿굞",
    "?뽯꺖",
    "癒?짗",
    "?뺤쒔",
    "怨쀬뵠",
    "濡쒓렇",
    "硫붿떆吏",
    "怨듭",
    "愿由",
    "뚯씪",
    "몄뀡",
    "쒕쾭",
    "꾩슂",
    "寃利",
    "?붾갑",
    "?꾨",
    "?뚯",
    "?몄",
    "?쒕",
    "?쇱",
    "?ы",
    "?좎",
    "?낅",
    "?ㅽ",
    "? ?",
)


def _tracked_text_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        names = result.stdout.splitlines()
    except Exception:
        names = [
            str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            for path in REPO_ROOT.rglob("*")
            if path.is_file()
        ]

    files: list[Path] = []
    for name in names:
        path = REPO_ROOT / name
        if not path.exists():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_FILENAMES:
            files.append(path)
    return sorted(files)


def _rel_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _has_forbidden_control_char(text: str) -> bool:
    for ch in text:
        codepoint = ord(ch)
        if ch in "\n\r\t":
            continue
        if codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
            return True
    return False


def _find_mojibake_issue(path: Path) -> str | None:
    rel_path = _rel_path(path)
    if rel_path in MOJIBAKE_ALLOWLIST or rel_path.endswith(MINIFIED_SKIP_SUFFIXES):
        return None

    text = path.read_text(encoding="utf-8", errors="replace")
    if "\ufffd" in text:
        return "contains replacement character U+FFFD"
    if _has_forbidden_control_char(text):
        return "contains unexpected control characters"

    for line_no, line in enumerate(text.splitlines(), 1):
        if any(token in line for token in MOJIBAKE_HINTS):
            snippet = line.strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            return f"line {line_no}: {snippet}"
    return None


def test_tracked_text_files_are_utf8_without_bom() -> None:
    offenders = [
        _rel_path(path)
        for path in _tracked_text_files()
        if path.read_bytes().startswith(UTF8_BOM)
    ]
    assert not offenders, "UTF-8 BOM found in: " + ", ".join(offenders)


def test_tracked_text_files_do_not_contain_mojibake() -> None:
    offenders: list[str] = []
    for path in _tracked_text_files():
        issue = _find_mojibake_issue(path)
        if issue:
            offenders.append(f"{_rel_path(path)} ({issue})")
    assert not offenders, "Mojibake detected in: " + ", ".join(offenders)
