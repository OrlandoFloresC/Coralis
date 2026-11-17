from __future__ import annotations

from dataclasses import asdict, dataclass

# error  = almost certainly wrong, must be reviewed
# aviso  = suspicious, worth a look
# info   = something the pipeline repaired or noticed; not a doubtful measure
SEVERITIES = ("error", "aviso", "info")


@dataclass
class Issue:
    rule: str
    severity: str
    message: str
    measure: int | None = None  # canonical measure index
    voice: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)
