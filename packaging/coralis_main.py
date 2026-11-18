"""Entry point of the packaged app (PyInstaller): the Coralis window."""

import sys

from omr_coral.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
