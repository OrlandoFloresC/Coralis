"""Detection, automatic installation and verification of external tools.

External tools are installed per-user (no admin rights needed) under the
platform data dir, e.g.:
  macOS   ~/Library/Application Support/omr-coral/tools
  Windows %LOCALAPPDATA%\\omr-coral\\tools
  Linux   ~/.local/share/omr-coral/tools
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

TOOLS_DIR = Path(user_data_dir("omr-coral", appauthor=False)) / "tools"


@dataclass
class ToolStatus:
    name: str
    ok: bool
    detail: str
    path: str | None = None
    required: bool = True


# --------------------------------------------------------------------------- helpers


def _download(url: str, dest: Path) -> None:
    print(f"  Descargando {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "omr-coral-installer"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / total:6.1%} de {total / 1e6:.0f} MB", end="", flush=True)
    print()
    tmp.replace(dest)


def _is_executable(p: Path) -> bool:
    return p.is_file() and (os.name == "nt" or os.access(p, os.X_OK))


# --------------------------------------------------------------------------- Audiveris


def _audiveris_asset(version: str) -> str:
    system, machine = platform.system(), platform.machine().lower()
    if system == "Darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
        return f"Audiveris-{version}-macosx-{arch}.dmg"
    if system == "Windows":
        # The "Console" build keeps stdout attached, which batch mode needs.
        return f"Audiveris-{version}-windowsConsole-x86_64.msi"
    if system == "Linux":
        if machine not in ("x86_64", "amd64"):
            raise RuntimeError(f"Audiveris no publica binarios para Linux {machine}; instálalo a mano.")
        return f"Audiveris-{version}-ubuntu22.04-x86_64.deb"
    raise RuntimeError(f"Sistema no soportado para instalar Audiveris: {system}")


def _audiveris_candidates(install_dir: Path) -> list[Path]:
    """Known executable locations: our private install first, then system installs."""
    c = [
        install_dir / "Audiveris.app" / "Contents" / "MacOS" / "Audiveris",
        *install_dir.rglob("Audiveris.exe"),
        *install_dir.rglob("bin/Audiveris"),
        Path("/Applications/Audiveris.app/Contents/MacOS/Audiveris"),
        Path.home() / "Applications/Audiveris.app/Contents/MacOS/Audiveris",
        Path("/opt/audiveris/bin/Audiveris"),
    ]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if os.environ.get(env):
            c.append(Path(os.environ[env]) / "Audiveris" / "Audiveris.exe")
    on_path = shutil.which("Audiveris") or shutil.which("audiveris")
    if on_path:
        c.append(Path(on_path))
    return c


def find_audiveris(cfg: dict) -> Path | None:
    configured = cfg["tools"].get("audiveris")
    if configured:
        p = Path(configured).expanduser()
        return p if _is_executable(p) else None
    install_dir = TOOLS_DIR / f"audiveris-{cfg['tools']['audiveris_version']}"
    for p in _audiveris_candidates(install_dir):
        if _is_executable(p):
            return p
    return None


def install_audiveris(cfg: dict) -> Path:
    version = cfg["tools"]["audiveris_version"]
    install_dir = TOOLS_DIR / f"audiveris-{version}"
    asset = _audiveris_asset(version)
    url = f"https://github.com/Audiveris/audiveris/releases/download/{version}/{asset}"
    print(f"Instalando Audiveris {version} en {install_dir}")
    pkg = TOOLS_DIR / "downloads" / asset
    if not pkg.exists():
        _download(url, pkg)
    with tempfile.TemporaryDirectory() as tmp:
        install_dir.mkdir(parents=True, exist_ok=True)
        system = platform.system()
        if system == "Darwin":
            mnt = Path(tmp) / "mnt"
            mnt.mkdir()
            # The DMG shows Audiveris' licence (GNU AGPL-3.0) and waits for "Y".
            print("  Audiveris se distribuye bajo la licencia GNU AGPL-3.0; se acepta para instalarlo.")
            r = subprocess.run(
                ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt), str(pkg)],
                input="Y\n", capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                raise RuntimeError(f"hdiutil no pudo montar {pkg.name}: {r.stderr.strip() or r.stdout.strip()}")
            try:
                app = next(mnt.glob("*.app"))
                dest = install_dir / "Audiveris.app"
                if dest.exists():
                    shutil.rmtree(dest)
                # ditto preserves the bundle's symlinks, permissions and signature.
                subprocess.run(["ditto", str(app), str(dest)], check=True)
            finally:
                subprocess.run(["hdiutil", "detach", str(mnt), "-quiet"], check=False)
        elif system == "Windows":
            # Administrative install = plain extraction, no admin rights or registry changes.
            # msiexec wants PROPERTY="value with spaces": pass the command line as written.
            subprocess.run(f'msiexec /a "{pkg}" /qn TARGETDIR="{install_dir}"', check=True)
        else:  # Linux .deb: extract without root
            subprocess.run(["dpkg-deb", "-x", str(pkg), str(install_dir)], check=True)
    exe = find_audiveris(cfg)
    if not exe:
        raise RuntimeError(f"Audiveris se descargó pero no encuentro el ejecutable en {install_dir}")
    print(f"  Audiveris instalado: {exe}")
    return exe


def audiveris_tessdata_dir() -> Path:
    """Folder where Audiveris looks for Tesseract language files (per its handbook)."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    if system == "Windows":
        # On Windows config and data share %APPDATA%, and Audiveris (5.11) reads the
        # languages from the config folder: "Installed OCR languages" lists only those.
        return base / "AudiverisLtd" / "audiveris" / "config" / "tessdata"
    return base / "AudiverisLtd" / "audiveris" / "tessdata"


def ensure_ocr_languages(cfg: dict) -> list[str]:
    """Download missing Tesseract models for the lyrics languages. Returns the missing ones it fetched."""
    langs = [l for l in (cfg["recognition"].get("lyrics_languages") or "").split("+") if l]
    tessdata = audiveris_tessdata_dir()
    fetched = []
    for lang in langs:
        dest = tessdata / f"{lang}.traineddata"
        if dest.exists():
            continue
        if not cfg["tools"].get("auto_install", True):
            raise RuntimeError(f"Falta el idioma OCR '{lang}' en {tessdata}")
        _download(f"https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata", dest)
        fetched.append(lang)
    return fetched


def ensure_audiveris(cfg: dict) -> Path:
    exe = find_audiveris(cfg)
    if not exe:
        if not cfg["tools"].get("auto_install", True):
            raise RuntimeError("Audiveris no está instalado y auto_install está desactivado.")
        exe = install_audiveris(cfg)
    ensure_ocr_languages(cfg)
    return exe


# --------------------------------------------------------------------------- homr
#
# homr is installed in its own virtual environment so its pinned dependencies
# never clash with ours, and it runs as a separate program.


def _homr_venv(cfg: dict) -> Path:
    return TOOLS_DIR / f"homr-{cfg['tools']['homr_version']}-venv"


def _venv_bin(venv: Path, name: str) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / (f"{name}.exe" if os.name == "nt" else name)


def find_homr(cfg: dict) -> Path | None:
    configured = cfg["tools"].get("homr")
    if configured:
        p = Path(configured).expanduser()
        return p if _is_executable(p) else None
    exe = _venv_bin(_homr_venv(cfg), "homr")
    return exe if _is_executable(exe) else None


def install_homr(cfg: dict) -> Path:
    import venv as venvmod

    version = cfg["tools"]["homr_version"]
    venv_dir = _homr_venv(cfg)
    print(f"Instalando homr {version} en {venv_dir} (licencia GNU AGPL-3.0)")
    venvmod.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    py = _venv_bin(venv_dir, "python")
    subprocess.run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([str(py), "-m", "pip", "install", "-q", f"homr[cpu]=={version}"], check=True)
    exe = _venv_bin(venv_dir, "homr")
    print("  Descargando los modelos de homr (solo la primera vez)...")
    subprocess.run([str(exe), "--init"], check=True, capture_output=True,
                   env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    print(f"  homr instalado: {exe}")
    return exe


def ensure_homr(cfg: dict) -> Path:
    exe = find_homr(cfg)
    if exe:
        return exe
    if not cfg["tools"].get("auto_install", True):
        raise RuntimeError("homr no está instalado y auto_install está desactivado.")
    return install_homr(cfg)


def homr_version(exe: Path) -> str | None:
    py = exe.parent / ("python.exe" if os.name == "nt" else "python")
    try:
        r = subprocess.run([str(py), "-c", "import importlib.metadata as m; print(m.version('homr'))"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None


# --------------------------------------------------------------------------- MuseScore (optional)


def find_musescore(cfg: dict) -> Path | None:
    configured = cfg["tools"].get("musescore")
    if configured:
        p = Path(configured).expanduser()
        return p if _is_executable(p) else None
    candidates = [
        Path("/Applications/MuseScore 4.app/Contents/MacOS/mscore"),
        Path(r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe"),
    ]
    for name in ("mscore4portable", "musescore4", "mscore", "musescore", "MuseScore4"):
        if w := shutil.which(name):
            candidates.append(Path(w))
    return next((p for p in candidates if _is_executable(p)), None)


# --------------------------------------------------------------------------- verification


_MINI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>S</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>
<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
<note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration><type>whole</type></note>
</measure></part></score-partwise>"""


def check_tools(cfg: dict, install: bool = True) -> list[ToolStatus]:
    results: list[ToolStatus] = []

    results.append(ToolStatus("Python", sys.version_info >= (3, 11), platform.python_version()))

    try:
        import music21
        from music21 import converter

        s = converter.parseData(_MINI_XML, format="musicxml")
        n = len(s.recurse().notes)
        results.append(ToolStatus("music21", n == 1, f"v{music21.__version__}, lectura MusicXML OK"))
    except Exception as e:  # noqa: BLE001
        results.append(ToolStatus("music21", False, f"error: {e}"))

    try:
        import verovio

        tk = verovio.toolkit()
        ok = tk.loadData(_MINI_XML) and "<svg" in tk.renderToSVG(1)
        results.append(ToolStatus("Verovio", ok, f"v{tk.getVersion()}, renderizado SVG {'OK' if ok else 'falló'}"))
    except Exception as e:  # noqa: BLE001
        results.append(ToolStatus("Verovio", False, f"error: {e}"))

    try:
        import pypdfium2

        results.append(ToolStatus("pypdfium2", True, f"v{pypdfium2.version.PYPDFIUM_INFO}"))
    except Exception as e:  # noqa: BLE001
        results.append(ToolStatus("pypdfium2", False, f"error: {e}"))

    try:
        import cv2

        results.append(ToolStatus("OpenCV", True, f"v{cv2.__version__}"))
    except Exception as e:  # noqa: BLE001
        results.append(ToolStatus("OpenCV", False, f"error: {e}"))

    try:
        exe = ensure_audiveris(cfg) if install else find_audiveris(cfg)
        if exe is None:
            results.append(ToolStatus("Audiveris", False, "no instalado"))
        else:
            ver = audiveris_version(exe)
            results.append(ToolStatus("Audiveris", bool(ver), ver or "no responde a -version", str(exe)))
    except Exception as e:  # noqa: BLE001
        results.append(ToolStatus("Audiveris", False, f"error: {e}"))

    if "homr" in cfg["recognition"]["engines"]:
        try:
            exe = ensure_homr(cfg) if install else find_homr(cfg)
            if exe is None:
                results.append(ToolStatus("homr", False, "no instalado"))
            else:
                ver = homr_version(exe)
                results.append(ToolStatus("homr", bool(ver), f"v{ver}" if ver else "no responde", str(exe)))
        except Exception as e:  # noqa: BLE001
            results.append(ToolStatus("homr", False, f"error: {e}"))

    ms = find_musescore(cfg)
    results.append(
        ToolStatus("MuseScore 4", ms is not None, "encontrado" if ms else "no encontrado (opcional)",
                   str(ms) if ms else None, required=False)
    )
    return results


def audiveris_version(exe: Path) -> str | None:
    try:
        r = subprocess.run([str(exe), "-batch", "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (r.stdout + r.stderr).splitlines()
    info = {}
    for line in lines:
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            info[key.strip()] = value.strip()
    if "Version" not in info:
        return None
    return f"v{info['Version']}, OCR: {info.get('OCR Engine', '?')}"
