"""Пути к данным: рядом с exe при сборке, рядом со скриптом при разработке."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_path(name: str) -> Path | None:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        path = Path(sys._MEIPASS) / name
        if path.exists():
            return path
    source = Path(__file__).resolve().parent / name
    return source if source.exists() else None


def ensure_file_beside_app(name: str) -> Path:
    """Копирует встроенный файл рядом с exe при первом запуске."""
    target = app_dir() / name
    if not target.exists():
        bundled = bundled_path(name)
        if bundled:
            shutil.copy(bundled, target)
    return target
