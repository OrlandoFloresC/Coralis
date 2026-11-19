"""Aviso de versión nueva."""

import sys

from omr_coral.gui import updates


def test_version_comparison():
    assert updates.is_newer("v0.3.1", "0.3.0")
    assert updates.is_newer("v0.10.0", "0.9.9")       # numbers, not text
    assert updates.is_newer("v1.0", "0.9.9")
    assert not updates.is_newer("v0.3.0", "0.3.0")
    assert not updates.is_newer("v0.2.0", "0.3.0")
    assert not updates.is_newer("prueba-19a025e", "0.3.0")  # a test build is never "newer"


def test_installer_for_this_computer(monkeypatch):
    assets = [{"name": "Coralis-0.4.0-Mac-chip-Apple.dmg", "browser_download_url": "mac"},
              {"name": "Coralis-0.4.0-Windows.exe", "browser_download_url": "win"}]
    monkeypatch.setattr(sys, "platform", "win32")
    assert updates.installer_for_this_computer(assets) == "win"
    monkeypatch.setattr(sys, "platform", "linux")
    assert updates.installer_for_this_computer(assets) is None


def test_no_internet_means_no_news(monkeypatch):
    def fail(*a, **k):
        raise OSError("sin internet")
    monkeypatch.setattr(updates.urllib.request, "urlopen", fail)
    assert updates.check() == {"available": False}
