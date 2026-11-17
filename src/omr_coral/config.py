"""Configuration loading: packaged defaults deep-merged with an optional user config.yaml."""

from __future__ import annotations

import copy
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    defaults = yaml.safe_load(
        resources.files("omr_coral").joinpath("default_config.yaml").read_text(encoding="utf-8")
    )
    candidate = Path(path) if path else Path.cwd() / "config.yaml"
    if candidate.is_file():
        user = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        return _deep_merge(defaults, user)
    if path:
        raise FileNotFoundError(f"No existe el archivo de configuración: {candidate}")
    return defaults
