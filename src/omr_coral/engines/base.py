"""Common interface for OMR engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EngineResult:
    engine: str
    image: Path
    musicxml: list[Path] = field(default_factory=list)
    log: Path | None = None
    ok: bool = False
    error: str | None = None
    warnings: list[str] = field(default_factory=list)


class Engine(ABC):
    name: str

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def ensure(self) -> None:
        """Install the engine if missing (called once before parallel recognition)."""

    @abstractmethod
    def recognize(self, pages: list[Path], out_dir: Path) -> EngineResult:
        """Recognize the given page images (in order), writing MusicXML file(s) into out_dir."""
