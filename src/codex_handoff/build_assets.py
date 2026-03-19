from __future__ import annotations

import math
from pathlib import Path

from codex_handoff import __version__


def write_build_assets(
    output_dir: Path,
    *,
    internal_name: str = "CodexHandoffSetup",
    original_filename: str = "CodexHandoffSetup.exe",
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    icon_path = output_dir / "codex-handoff.ico"
    version_path = output_dir / "version_info.txt"
    icon_path.write_bytes(build_icon_bytes())
    version_path.write_text(
        build_version_info_text(
            internal_name=internal_name,
            original_filename=original_filename,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return icon_path, version_path


def versioned_executable_name(
    base_name: str = "CodexHandoffSetup",
    *,
    version: str = __version__,
) -> str:
    normalized_version = version.lstrip("v")
    return f"{base_name}-{normalized_version}.exe"


def build_version_info_text(
    *,
    internal_name: str = "CodexHandoffSetup",
    original_filename: str = "CodexHandoffSetup.exe",
) -> str:
    major, minor, patch = parse_version(__version__)
    version = f"{major}.{minor}.{patch}.0"
    tuple_text = f"({major}, {minor}, {patch}, 0)"
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tuple_text},
    prodvers={tuple_text},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Codex OSS'),
          StringStruct('FileDescription', 'Codex Handoff Setup'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', '{internal_name}'),
          StringStruct('OriginalFilename', '{original_filename}'),
          StringStruct('ProductName', 'Codex Handoff'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def build_icon_bytes() -> bytes:
    size = 64
    pixels = _build_icon_pixels(size)
    return _encode_ico(size, pixels)


def parse_version(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) < 3:
        raise ValueError(f"Version must have at least three parts: {value}")
    return tuple(int(part) for part in parts[:3])  # type: ignore[return-value]


def _build_icon_pixels(size: int) -> list[tuple[int, int, int, int]]:
    pixels: list[tuple[int, int, int, int]] = []
    center = (size - 1) / 2
    outer = size * 0.34
    inner = size * 0.20

    for y in range(size):
        for x in range(size):
            bg = _background_color(x, y, size)
            dx = x - center
            dy = y - center
            dist = math.sqrt(dx * dx + dy * dy)
            angle = math.degrees(math.atan2(dy, dx))

            color = bg
            if outer >= dist >= inner and not (-42 <= angle <= 42 and x > center):
                color = (244, 247, 250, 255)

            if abs(dx) < 3 and -outer * 0.55 <= dy <= outer * 0.55:
                color = (23, 36, 44, 255)

            if (x - (center + 11)) ** 2 + (y - (center - 14)) ** 2 <= 18:
                color = (108, 226, 198, 255)

            pixels.append(color)
    return pixels


def _background_color(x: int, y: int, size: int) -> tuple[int, int, int, int]:
    blend = (x + y) / max(1, (size - 1) * 2)
    red = int(18 + (38 - 18) * blend)
    green = int(88 + (138 - 88) * blend)
    blue = int(128 + (181 - 128) * blend)
    return (red, green, blue, 255)


def _encode_ico(size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    image = bytearray()
    image.extend((40).to_bytes(4, "little"))  # BITMAPINFOHEADER size
    image.extend(size.to_bytes(4, "little", signed=True))
    image.extend((size * 2).to_bytes(4, "little", signed=True))
    image.extend((1).to_bytes(2, "little"))  # planes
    image.extend((32).to_bytes(2, "little"))  # bits per pixel
    image.extend((0).to_bytes(4, "little"))  # compression
    image.extend((size * size * 4).to_bytes(4, "little"))
    image.extend((0).to_bytes(4, "little"))  # x ppm
    image.extend((0).to_bytes(4, "little"))  # y ppm
    image.extend((0).to_bytes(4, "little"))  # colors used
    image.extend((0).to_bytes(4, "little"))  # important colors

    for row in range(size - 1, -1, -1):
        for col in range(size):
            red, green, blue, alpha = pixels[row * size + col]
            image.extend(bytes((blue, green, red, alpha)))

    mask_row_bytes = ((size + 31) // 32) * 4
    image.extend(b"\x00" * (mask_row_bytes * size))

    icon_dir = bytearray()
    icon_dir.extend((0).to_bytes(2, "little"))
    icon_dir.extend((1).to_bytes(2, "little"))
    icon_dir.extend((1).to_bytes(2, "little"))
    icon_dir.extend(bytes((size if size < 256 else 0, size if size < 256 else 0, 0, 0)))
    icon_dir.extend((1).to_bytes(2, "little"))
    icon_dir.extend((32).to_bytes(2, "little"))
    icon_dir.extend(len(image).to_bytes(4, "little"))
    icon_dir.extend((6 + 16).to_bytes(4, "little"))
    return bytes(icon_dir + image)
