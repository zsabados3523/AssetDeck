"""Janela dos visualizadores 3D — HDRI e modelo na MESMA casca (Fatia 90).

Fase 7, Etapa 3. Antes eram duas `QDialog` separadas (`HdriViewer` e
`ModelViewer`), cada uma montada à mão, com layouts levemente diferentes
sem motivo: status espremido no canto de cima, nenhum nome de asset
dentro da janela (só na barra de título do gerenciador), botões
quadrados onde o resto do app já usa pastilha, e nenhum jeito de fechar
sem ser Esc ou o ✕ do sistema.

**Por que continua sendo janela PRÓPRIA e não overlay embutido.** O
pedido original do Rafael era que estes dois virassem overlay dentro da
janela principal, como o `PreviewPopup`. Isso já foi tentado e revertido
no mesmo dia (Fatia 65): um `QOpenGLWidget` em qualquer lugar da árvore
de widgets de um top-level muda o modo de composição da JANELA INTEIRA
daquele top-level na primeira vez que aparece — com o GL dentro da
`MainWindow`, era o AssetDeck todo que piscava, não uma janelinha. O
`PreviewPopup` pode ser embutido porque não usa OpenGL.

**Por que UMA janela para os dois.** É a mesma transição de composição
descrita acima que o `prewarm_gl_viewers` da `MainWindow` paga na
abertura do app, mostrando e escondendo os visualizadores fora da tela.
Duas janelas = duas transições. Juntando os dois `QOpenGLWidget` num
`QStackedWidget` da MESMA janela, a transição acontece uma vez só —
metade do custo de pré-aquecimento, sem mudar nada do que aparece na
tela.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from assetdeck.ui import hdri_viewer, icons, model_viewer, theme

log = logging.getLogger(__name__)

# Raio dos cantos do palco (a área do OpenGL). Mesmo valor do cartão do
# `PreviewPopup` — as duas são "a superfície onde o asset aparece".
RAIO_PALCO = 14

PAGINA_HDRI = 0
PAGINA_MODELO = 1

# Largura máxima do nome no cabeçalho antes de elidir. É um número fixo de
# propósito: elidir reagindo ao tamanho do widget foi exatamente o que fez o
# painel de detalhes piscar na Fatia 79 (o texto muda -> o layout recalcula ->
# o texto muda de novo). Aqui a elisão acontece UMA vez, ao abrir.
LARGURA_NOME = 520


def posicao_centralizada(area: QRect, tam: QSize, limite: QRect | None = None) -> QPoint:
    """Canto superior-esquerdo que deixa `tam` centralizado em `area`.

    Pedido explícito do Rafael: a janela do visualizador tem de abrir
    centralizada NO APLICATIVO, não onde o gerenciador de janelas resolver
    (que no Zorin é geralmente o centro da TELA, ou pior, empilhada com um
    deslocamento a cada abertura).

    `limite` (a área útil do monitor) evita o efeito colateral óbvio: se a
    janela principal estiver encostada num canto, ou for menor que o
    visualizador, centralizar nela jogaria metade do visualizador pra fora
    da tela. Função pura — a parte que dá pra testar sem contexto OpenGL.
    """
    x = area.x() + (area.width() - tam.width()) // 2
    y = area.y() + (area.height() - tam.height()) // 2
    if limite is not None:
        x = max(limite.x(), min(x, limite.x() + limite.width() - tam.width()))
        y = max(limite.y(), min(y, limite.y() + limite.height() - tam.height()))
    return QPoint(x, y)


class _CantosDoPalco(QWidget):
    """Arredonda os cantos da superfície OpenGL, por cima dela.

    `border-radius` do QSS não alcança um `QOpenGLWidget` (ele pinta pelo
    GL, não pelo estilo) e `setMask()` recorta sem antialias — os cantos
    saem serrilhados, o que ficaria pior do que deixar quadrado. Este
    widget fica POR CIMA do palco, transparente pro mouse, e pinta só o
    que sobra FORA do retângulo arredondado, com a cor de fundo da janela,
    mais o contorno por cima. Antialiasing de verdade e nenhuma máscara.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, event) -> None:  # noqa: N802
        cores = theme.current_colors()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Meio pixel pra dentro: um contorno de 1px desenhado EM CIMA da
        # borda inteira sai cortado pela metade.
        moldura = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        fora = QPainterPath()
        fora.addRect(QRectF(self.rect()))
        dentro = QPainterPath()
        dentro.addRoundedRect(moldura, RAIO_PALCO, RAIO_PALCO)
        pintor.fillPath(fora.subtracted(dentro), QColor(cores["bg"]))

        r, g, b, alfa = cores["border"]
        pintor.setPen(QPen(QColor(r, g, b, round(alfa * 255)), 1))
        pintor.setBrush(Qt.BrushStyle.NoBrush)
        pintor.drawRoundedRect(moldura, RAIO_PALCO, RAIO_PALCO)


class VisualizadorWindow(QDialog):
    """Casca única: cabeçalho (nome + extensão + fechar), controles do modo,
    palco do OpenGL e rodapé de status."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window)
        self.resize(1000, 660)

        # ---- cabeçalho ----
        self.titulo = QLabel("—")
        self.titulo.setObjectName("title")  # mesmo estilo do título do preview
        self.chip = QLabel()
        self.chip.setObjectName("chipForte")  # mesma pastilha do painel de detalhes
        self.btn_fechar = QPushButton()
        self.btn_fechar.setObjectName("ghost")
        self.btn_fechar.setToolTip("Fechar (Esc)")
        self.btn_fechar.setFixedWidth(38)
        self.btn_fechar.clicked.connect(self.close)

        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(8)
        cabecalho.addWidget(self.titulo)
        cabecalho.addWidget(self.chip)
        cabecalho.addStretch(1)
        cabecalho.addWidget(self.btn_fechar)

        # ---- controles (o que aparece depende da página) ----
        self.btn_ambiente = QToolButton()
        self.btn_ambiente.setText("Ambiente")
        self.btn_esfera = QToolButton()
        self.btn_esfera.setText("Esfera de reflexo")
        self._modos = QButtonGroup(self)
        self._modos.setExclusive(True)
        for indice, botao in ((hdri_viewer.MODO_AMBIENTE, self.btn_ambiente),
                              (hdri_viewer.MODO_ESFERA, self.btn_esfera)):
            botao.setObjectName("pill")
            botao.setCheckable(True)
            self._modos.addButton(botao, indice)
            botao.clicked.connect(lambda _c=False, m=indice: self.hdri.set_modo(m))
        self.btn_ambiente.setChecked(True)

        self.btn_enquadrar = QToolButton()
        self.btn_enquadrar.setObjectName("pill")
        self.btn_enquadrar.setText("Enquadrar")
        self.btn_enquadrar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_enquadrar.setToolTip("Recentraliza a câmera no modelo")
        self.btn_enquadrar.clicked.connect(self._enquadrar)

        controles = QHBoxLayout()
        controles.setSpacing(8)
        controles.addWidget(self.btn_ambiente)
        controles.addWidget(self.btn_esfera)
        controles.addWidget(self.btn_enquadrar)
        controles.addStretch(1)

        # ---- palco (as duas superfícies de OpenGL) ----
        self.hdri = hdri_viewer.HdriGLView()
        self.modelo = model_viewer.ModelGLView()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.hdri)
        self.stack.addWidget(self.modelo)

        self._palco = QWidget()
        palco_layout = QVBoxLayout(self._palco)
        palco_layout.setContentsMargins(0, 0, 0, 0)
        palco_layout.addWidget(self.stack)
        self._cantos = _CantosDoPalco(self._palco)
        self._palco.installEventFilter(self)

        # ---- rodapé ----
        self.status = QLabel("Carregando…")
        self.status.setObjectName("muted")
        self.dica = QLabel("Esc fecha")
        self.dica.setObjectName("visorDica")
        rodape = QHBoxLayout()
        rodape.addWidget(self.status)
        rodape.addStretch(1)
        rodape.addWidget(self.dica)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 14, 16, 14)
        raiz.setSpacing(12)
        raiz.addLayout(cabecalho)
        raiz.addLayout(controles)
        raiz.addWidget(self._palco, stretch=1)
        raiz.addLayout(rodape)

        # Um emissor POR TIPO, criado uma vez: a carga roda em thread e
        # precisa de um dono vivo do outro lado do sinal.
        self._alvo: Path | None = None
        self._sig_hdri = hdri_viewer.SinalCarga()
        self._sig_hdri.loaded.connect(self._hdri_carregado)
        self._sig_hdri.failed.connect(self._falhou)
        self._sig_modelo = model_viewer.SinalCarga()
        self._sig_modelo.loaded.connect(self._modelo_carregado)
        self._sig_modelo.failed.connect(self._falhou)

        self.refresh_theme()

    # ---- abertura ----

    def abrir_hdri(self, path: Path) -> None:
        self.hdri.camera.reset()
        self._preparar(path, PAGINA_HDRI, "Carregando…")
        hdri_viewer.iniciar_carga(self._sig_hdri, path)

    def abrir_modelo(self, path: Path, content_hash: str | None = None) -> None:
        """`content_hash` só é usado pelo loader de `.blend` (cache da
        exportação via Blender) — as outras extensões ignoram."""
        recado = ("Lendo geometria do .blend (via Blender)…"
                  if path.suffix.lower() == ".blend" else "Carregando…")
        self._preparar(path, PAGINA_MODELO, recado)
        model_viewer.iniciar_carga(self._sig_modelo, path, content_hash)

    def _preparar(self, path: Path, pagina: int, recado: str) -> None:
        self._alvo = path
        rotulo = "HDRI" if pagina == PAGINA_HDRI else "Modelo"
        self.setWindowTitle(f"{rotulo} — {path.name}")
        metricas = QFontMetrics(self.titulo.font())
        self.titulo.setText(
            metricas.elidedText(path.stem, Qt.TextElideMode.ElideRight, LARGURA_NOME))
        self.titulo.setToolTip(path.name)
        self.chip.setText(path.suffix.upper().lstrip("."))
        self.stack.setCurrentIndex(pagina)
        self.btn_ambiente.setVisible(pagina == PAGINA_HDRI)
        self.btn_esfera.setVisible(pagina == PAGINA_HDRI)
        self.btn_enquadrar.setVisible(pagina == PAGINA_MODELO)
        self.status.setText(recado)
        self.centralizar_no_app()
        # Tirar o "minimizada" antes de mostrar (Fatia 93): se o Rafael
        # minimizar o visualizador e der duplo clique noutro asset, `show()`
        # sozinho NÃO desminimiza — a janela carregaria o novo asset ainda no
        # dock, parecendo que o clique não fez nada.
        #
        # Isto cobre só esse caso. O outro caminho pro mesmo sintoma — o
        # pré-aquecimento deixando a janela iconificada no gerenciador — NÃO
        # se conserta daqui: o gerenciador reaplica o estado dele DEPOIS do
        # `show()`, então mexer no estado antes não adianta (medido). Aquele
        # está resolvido na origem, em `prewarm_gl_viewers`.
        #
        # Só o bit de minimizada, em vez de `showNormal()`: quem maximizou a
        # janela continua com ela maximizada no próximo asset.
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def centralizar_no_app(self) -> None:
        """Abre no centro da JANELA PRINCIPAL (pedido do Rafael), presa à
        área útil do monitor pra nunca nascer meio pra fora da tela."""
        pai = self.parentWidget()
        janela = pai.window() if pai is not None else None
        tela = self.screen() or (janela.screen() if janela is not None else None)
        limite = tela.availableGeometry() if tela is not None else None
        area = janela.frameGeometry() if janela is not None else limite
        if area is None:
            return
        self.move(posicao_centralizada(area, self.size(), limite))

    # ---- geometria dos cantos ----

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._palco and event.type() == QEvent.Type.Resize:
            self._cantos.setGeometry(self._palco.rect())
            self._cantos.raise_()
        return super().eventFilter(obj, event)

    # ---- resultado das cargas ----

    def _hdri_carregado(self, imagem) -> None:
        log.info("HDRI pronto na tela: %s (%d × %d)",
                 getattr(self._alvo, "name", "?"), imagem.width(), imagem.height())
        self.hdri.set_image(imagem)
        self.status.setText(
            f"{imagem.width()} × {imagem.height()} px  ·  "
            "arraste para girar, duplo clique centraliza")

    def _modelo_carregado(self, malha) -> None:
        log.info("Modelo pronto na tela: %s (%d vértices)",
                 getattr(self._alvo, "name", "?"), len(malha.positions))
        self.modelo.set_mesh(malha)
        n_tris = len(malha.positions) // 3
        self.status.setText(
            f"{n_tris:n} triângulos  ·  arraste para orbitar, roda pra zoom")

    def _falhou(self, mensagem: str) -> None:
        log.error("Visualizador não conseguiu abrir %s: %s",
                  getattr(self._alvo, "name", "?"), mensagem)
        self.status.setText(f"Não consegui abrir: {mensagem}")

    def _enquadrar(self) -> None:
        self.modelo.enquadrar()

    # ---- tema ----

    def refresh_theme(self) -> None:
        """Ícones tingidos à mão (não passam pelo QSS) e os cantos do palco,
        que são pintados com a cor de fundo do tema — mesmo padrão do
        seletor de biblioteca e das seções do painel de detalhes."""
        cores = theme.current_colors()
        self.btn_fechar.setIcon(icons.icon("x", cores["text_muted"], 16))
        self.btn_enquadrar.setIcon(icons.icon("enquadrar", cores["text"], 16))
        self._cantos.update()

    # ---- fechar ----

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Libera a textura do HDRI na GPU (32MB num 4K). Só o HDRI tem o quê
        # liberar; a malha do modelo vive num VBO que o Qt derruba junto com
        # o contexto.
        self.hdri.cleanup()
        super().closeEvent(event)
