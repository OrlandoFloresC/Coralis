from .base import Engine, EngineResult


def get_engine(name: str, cfg: dict) -> Engine:
    if name == "audiveris":
        from .audiveris import AudiverisEngine

        return AudiverisEngine(cfg)
    if name == "homr":
        from .homr import HomrEngine

        return HomrEngine(cfg)
    raise ValueError(f"Motor desconocido: {name}")


__all__ = ["Engine", "EngineResult", "get_engine"]
