"""Is there a newer Coralis? Asks GitHub for the latest published release.

Only reads public information (no account, nothing sent about the user). Any failure
(no internet, GitHub down, a slow network) means "no news": the window just opens.
"""

from __future__ import annotations

import json
import platform
import re
import sys
import urllib.request

from .. import __version__

REPO = "OrlandoFloresC/Coralis"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def _numbers(version: str) -> tuple[int, ...]:
    """'v0.3.1' -> (0, 3, 1); anything that is not a plain version -> () (never newer)."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", version.strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def is_newer(latest: str, current: str) -> bool:
    a, b = _numbers(latest), _numbers(current)
    if not a or not b:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def installer_for_this_computer(assets: list[dict]) -> str | None:
    """Download link of the installer that fits this system, if the release has one."""
    if sys.platform == "win32":
        wanted = "-Windows.exe"
    elif sys.platform == "darwin" and platform.machine().lower() in ("arm64", "aarch64"):
        wanted = "-Mac-chip-Apple.dmg"
    else:
        return None
    return next((a["browser_download_url"] for a in assets if a.get("name", "").endswith(wanted)), None)


def check(timeout: float = 6.0) -> dict:
    """{"available": bool, "version": "0.4.0", "download": url or None, "page": url}."""
    from ..tools import _ssl_context

    try:
        req = urllib.request.Request(LATEST, headers={"User-Agent": "Coralis", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            data = json.load(resp)
    except Exception:  # noqa: BLE001  (offline, rate-limited, anything: no news)
        return {"available": False}
    latest = str(data.get("tag_name", ""))
    if not is_newer(latest, __version__):
        return {"available": False}
    return {"available": True, "version": latest.lstrip("v"), "current": __version__,
            "download": installer_for_this_computer(data.get("assets") or []),
            "page": data.get("html_url") or f"https://github.com/{REPO}/releases/latest"}
