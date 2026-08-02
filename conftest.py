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


@pytest.fixture
def qt_settle(qapp):
    """Função de teardown que faz deleteLater() destruir de verdade.

    QCoreApplication.processEvents() sozinho NÃO despacha eventos
    DeferredDelete — é comportamento documentado do Qt, para não destruir um
    objeto no meio de uma iteração do loop que ainda o está usando. Sem essa
    chamada extra, um widget "fechado" com deleteLater() continua vivo em
    QApplication.allWidgets() indefinidamente, e cada teste seguinte que cria
    widgets vai acumulando zumbis — o que deixa qualquer código que depois
    chame QApplication.setStyleSheet() (ex.: ui.theme.apply_theme) cada vez
    mais lento conforme a suíte roda.

    Passa o widget explicitamente como `receiver` (nunca None): com None,
    sendPostedEvents varre TODO DeferredDelete pendente na aplicação inteira,
    inclusive de widgets que outros testes fecharam sem destruir — derrubando
    objetos ainda em uso fora de ordem (visto travar com segfault ao rodar a
    suíte inteira).
    """
    from PySide6.QtCore import QEvent

    def _settle(*widgets) -> None:
        for w in widgets:
            w.deleteLater()
            qapp.sendPostedEvents(w, QEvent.Type.DeferredDelete)
        qapp.processEvents()

    return _settle
