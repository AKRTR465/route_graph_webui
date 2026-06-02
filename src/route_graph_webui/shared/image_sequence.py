from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp"}


def natural_text_key(text: str) -> list[object]:
    parts = re.split(r"(\d+)", text)
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key


def natural_sort_key(path: Path) -> list[object]:
    key = natural_text_key(path.stem)
    key.append(path.suffix.lower())
    return key


def collect_image_files(
    directory: str | Path,
    *,
    extensions: Iterable[str] = SUPPORTED_IMAGE_EXTENSIONS,
) -> list[Path]:
    root = Path(directory)
    normalized_extensions = {str(extension).lower() for extension in extensions}
    images = [
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in normalized_extensions
    ]
    images.sort(key=natural_sort_key)
    return images


def find_image_directories(
    source_root: str | Path,
    *,
    extensions: Iterable[str] = SUPPORTED_IMAGE_EXTENSIONS,
) -> list[Path]:
    root = Path(source_root)
    normalized_extensions = {str(extension).lower() for extension in extensions}
    image_dirs: list[Path] = []
    for current_root, _, filenames in os.walk(root):
        if any(Path(name).suffix.lower() in normalized_extensions for name in filenames):
            image_dirs.append(Path(current_root))
    image_dirs.sort(key=lambda path: natural_text_key(str(path.relative_to(root))))
    return image_dirs


__all__ = [
    "SUPPORTED_IMAGE_EXTENSIONS",
    "collect_image_files",
    "find_image_directories",
    "natural_sort_key",
    "natural_text_key",
]
