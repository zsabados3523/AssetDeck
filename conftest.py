# Presença deste arquivo na raiz faz o pytest incluir o projeto no sys.path,
# permitindo "import assetdeck" nos testes sem instalação do pacote.
import os

# Testes de UI rodam sem tela (headless) — precisa valer antes de qualquer Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    """QApplication única para os testes que tocam widgets."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
