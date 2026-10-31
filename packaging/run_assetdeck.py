"""Ponto de entrada do executável empacotado com PyInstaller."""
from __future__ import annotations

import sys
from assetdeck.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
