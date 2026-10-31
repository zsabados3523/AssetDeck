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


@pytest.fixture(autouse=True)
def _cleanup_qt_widgets():
    """Fecha e agenda exclusão de todos os widgets de topo criados pelo teste."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication, QEvent
    import shiboken6

    app = QApplication.instance()
    initial_top_levels = set(app.topLevelWidgets()) if app else set()

    yield

    app = QApplication.instance()
    if not app:
        return

    for widget in list(app.topLevelWidgets()):
        if widget not in initial_top_levels and shiboken6.isValid(widget):
            widget.close()
            widget.deleteLater()

    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
