#!/usr/bin/env python3
"""One-step installer for omr-coral (works on Windows, macOS and Linux).

    python instalar.py

Creates a virtual environment in .venv, installs the package and its Python
dependencies, then downloads and verifies the external tools (Audiveris...).
Uses only the standard library so it runs on a fresh Python install.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"


def main() -> int:
    if sys.version_info < (3, 11):
        print(f"Se necesita Python 3.11 o superior (tienes {sys.version.split()[0]}).")
        print("Descárgalo desde https://www.python.org/downloads/")
        return 1
    if not VENV.exists():
        print(f"Creando entorno virtual en {VENV}")
        venv.EnvBuilder(with_pip=True).create(VENV)
    bindir = VENV / ("Scripts" if sys.platform == "win32" else "bin")
    py = bindir / ("python.exe" if sys.platform == "win32" else "python")
    print("Instalando dependencias de Python...")
    subprocess.run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([str(py), "-m", "pip", "install", "-q", "-e", f"{ROOT}[dev]"], check=True)
    print("Instalando y verificando herramientas externas...")
    env = {**os.environ, "PYTHONUTF8": "1"}  # Windows consoles default to cp1252
    rc = subprocess.run([str(py), "-m", "omr_coral.cli", "setup"], env=env).returncode
    if rc == 0:
        omr = bindir / ("omr.exe" if sys.platform == "win32" else "omr")
        print(f"\nListo. Uso:\n  {omr} recognize input/mi_partitura.pdf")
    return rc


if __name__ == "__main__":
    sys.exit(main())
