from __future__ import annotations

from pathlib import Path

UTF8_BOM = b"\xef\xbb\xbf"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return read_text(path)


def write_text(path: Path, content: str, *, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8-sig" if bom else "utf-8"
    path.write_text(_normalize_newlines(content), encoding=encoding, newline="\n")


def append_text(path: Path, content: str) -> None:
    existing = read_optional_text(path)
    if existing and not existing.endswith("\n"):
        existing += "\n"
    write_text(path, f"{existing}{_normalize_newlines(content)}")


def has_utf8_bom(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("rb") as handle:
        prefix = handle.read(3)
    return prefix.startswith(UTF8_BOM)


def strip_first_heading(markdown: str) -> str:
    lines = _normalize_newlines(markdown).split("\n")
    if lines and lines[0].lstrip().startswith("#"):
        index = 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        lines = lines[index:]
    return "\n".join(lines).strip()


def parse_markdown_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in _normalize_newlines(markdown).split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def markdown_body_or_fallback(markdown: str, fallback: str) -> str:
    content = markdown.strip()
    return content if content else fallback


def to_posix_path(path: str) -> str:
    return path.replace("\\", "/")


def _normalize_newlines(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")
