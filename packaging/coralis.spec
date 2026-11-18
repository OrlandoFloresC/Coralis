# PyInstaller recipe for the Coralis app.
#   macOS (Apple chip):  pyinstaller packaging/coralis.spec  ->  dist/Coralis.app
# Audiveris, homr and the OCR languages are not inside: the app downloads them on its
# first run (see omr_coral/tools.py), into the user's data folder.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
ICON_MAC = str(ROOT / "assets" / "coralis.icns")
ICON_WIN = str(ROOT / "assets" / "coralis.ico")

datas = []
datas += collect_data_files("omr_coral")  # config, report template, window HTML and icons
datas += collect_data_files("verovio")    # music fonts for drawing measures
# music21 without its corpus of example scores (66 MB we never use)
datas += [d for d in collect_data_files("music21") if "/corpus/" not in d[0].replace("\\", "/")]
datas += collect_data_files("certifi")

hiddenimports = collect_submodules("omr_coral") + collect_submodules("music21")
hiddenimports = [h for h in hiddenimports if not h.startswith("music21.corpus.") and ".test" not in h]

a = Analysis(
    [str(ROOT / "packaging" / "coralis_main.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "scipy", "pandas", "PyQt5", "PyQt6", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Coralis",
    console=False,
    icon=ICON_WIN if sys.platform == "win32" else ICON_MAC,
    target_arch="arm64" if sys.platform == "darwin" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Coralis")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Coralis.app",
        icon=ICON_MAC,
        bundle_identifier="io.github.orlandofloresc.coralis",
        info_plist={
            "CFBundleName": "Coralis",
            "CFBundleDisplayName": "Coralis",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSDocumentsFolderUsageDescription": "Coralis guarda las partituras convertidas en Documentos/Coralis.",
        },
    )
