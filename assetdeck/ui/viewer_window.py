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

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
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
        self.resize(1240, 720)

        # ---- cabeçalho ----
        self.titulo = QLabel("—")
        self.titulo.setObjectName("pageTitle")
        self.titulo.setAccessibleName("Nome do asset visualizado")
        self.chip = QLabel()
        self.chip.setObjectName("chipMini")
        self.chip.setAccessibleName("Formato do arquivo")
        # Sem ✕ próprio (Fatia 94, Rafael: "tem o botão de fechar porém ainda
        # sim tem os botões de qualquer janela, então fica meio redundante").
        # Esta é uma janela normal do sistema: minimizar/maximizar/fechar já
        # vêm na barra de título, e um segundo ✕ logo abaixo do primeiro só
        # confunde. Quem quiser teclado tem o Esc, dito no rodapé.
        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(8)
        cabecalho.addWidget(self.titulo)
        cabecalho.addWidget(self.chip)
        cabecalho.addStretch(1)

        # ---- controles (o que aparece depende da página) ----
        self.btn_ambiente = QToolButton()
        self.btn_ambiente.setText("Ambiente")
        self.btn_ambiente.setAccessibleName("Modo de iluminação: ambiente")
        self.btn_esfera = QToolButton()
        self.btn_esfera.setText("Esfera de reflexo")
        self.btn_esfera.setAccessibleName("Modo de iluminação: esfera de reflexo")
        self._modos = QButtonGroup(self)
        self._modos.setExclusive(True)
        for indice, botao in ((hdri_viewer.MODO_AMBIENTE, self.btn_ambiente),
                              (hdri_viewer.MODO_ESFERA, self.btn_esfera)):
            botao.setObjectName("pillMini")
            botao.setCheckable(True)
            self._modos.addButton(botao, indice)
            botao.clicked.connect(lambda _c=False, m=indice: self.hdri.set_modo(m))
        self.btn_ambiente.setChecked(True)

        self.btn_enquadrar = QToolButton()
        self.btn_enquadrar.setObjectName("pillMini")
        self.btn_enquadrar.setText("Enquadrar")
        self.btn_enquadrar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_enquadrar.setToolTip("Recentraliza a câmera no modelo")
        self.btn_enquadrar.setAccessibleName("Enquadrar modelo")
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

        # Inspetor lateral com estatísticas e os materiais realmente lidos
        # pelo loader. Não transforma isso em um bloco de texto no rodapé:
        # números e nomes continuam visíveis enquanto se orbita o modelo.
        self.info_heading = QLabel("INFORMAÇÕES")
        self.info_heading.setObjectName("viewerInfoHeading")
        self.stat_values: dict[str, QLabel] = {}
        stats = QVBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(2)
        stats.addWidget(self.info_heading)
        for chave, rotulo in (
            ("format", "Formato"), ("resolution", "Resolução"),
            ("vertices", "Vértices"), ("triangles", "Triângulos"),
            ("materials", "Materiais"), ("textures", "Texturas"),
        ):
            valor = QLabel("—")
            self.stat_values[chave] = valor
            stats.addWidget(self._info_row(rotulo, valor))

        self.materials_heading = QLabel("MATERIAIS")
        self.materials_heading.setObjectName("viewerInfoHeading")
        self.materials_list = QWidget()
        self.materials_list.setObjectName("viewerMaterialsList")
        self.materials_layout = QVBoxLayout(self.materials_list)
        self.materials_layout.setContentsMargins(0, 0, 0, 0)
        self.materials_layout.setSpacing(5)
        self.materials_placeholder = QLabel("Nenhum material carregado")
        self.materials_placeholder.setObjectName("muted")
        self.materials_placeholder.setWordWrap(True)
        self.materials_layout.addWidget(self.materials_placeholder)
        self.materials_layout.addStretch(1)

        materials_scroll = QScrollArea()
        materials_scroll.setWidgetResizable(True)
        materials_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        materials_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        materials_scroll.setWidget(self.materials_list)
        self.materials_scroll = materials_scroll

        inspector = QWidget()
        inspector.setObjectName("viewerInspector")
        inspector.setMinimumWidth(228)
        inspector.setMaximumWidth(276)
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(0, 2, 0, 0)
        inspector_layout.setSpacing(10)
        inspector_layout.addLayout(stats)
        inspector_layout.addWidget(self.materials_heading)
        inspector_layout.addWidget(materials_scroll, 1)
        self.inspector = inspector

        palco_divider = QFrame()
        palco_divider.setObjectName("viewerDivider")
        palco_divider.setFrameShape(QFrame.Shape.VLine)
        palco_divider.setFixedWidth(1)
        workspace = QHBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(18)
        workspace.addWidget(self._palco, 1)
        workspace.addWidget(palco_divider)
        workspace.addWidget(inspector)

        # ---- rodapé ----
        self.status = QLabel("Carregando…")
        self.status.setObjectName("muted")
        self.status.setAccessibleName("Estado da visualização 3D")
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
        raiz.addLayout(workspace, stretch=1)
        raiz.addLayout(rodape)

        # Um emissor POR TIPO, criado uma vez: a carga roda em thread e
        # precisa de um dono vivo do outro lado do sinal.
        self._alvo: Path | None = None
        self._abrindo = False
        self._sig_hdri = hdri_viewer.SinalCarga()
        self._sig_hdri.loaded.connect(self._hdri_carregado)
        self._sig_hdri.failed.connect(self._falhou)
        self._sig_modelo = model_viewer.SinalCarga()
        self._sig_modelo.loaded.connect(self._modelo_carregado)
        self._sig_modelo.failed.connect(self._falhou)

        self.refresh_theme()

    @staticmethod
    def _info_row(rotulo: str, valor: QLabel) -> QWidget:
        texto = QLabel(rotulo)
        texto.setObjectName("viewerInfoLabel")
        valor.setObjectName("viewerInfoValue")
        valor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        linha = QWidget()
        layout = QHBoxLayout(linha)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(8)
        layout.addWidget(texto)
        layout.addStretch(1)
        layout.addWidget(valor)
        linha.setFixedHeight(30)
        return linha

    def _clear_material_rows(self) -> None:
        while self.materials_layout.count():
            item = self.materials_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_materials(self, materials) -> None:
        self._clear_material_rows()
        self.materials_heading.setVisible(bool(materials))
        if not materials:
            empty = QLabel("Nenhum material carregado")
            empty.setObjectName("muted")
            self.materials_layout.addWidget(empty)
            self.materials_layout.addStretch(1)
            return

        vistos: set[tuple] = set()
        for material in materials:
            textura = material.texture
            chave = (material.name, str(textura) if textura else None, material.color)
            if chave in vistos:
                continue
            vistos.add(chave)
            nome = material.name or f"Material {len(vistos)}"
            item = QWidget()
            item.setObjectName("viewerMaterialRow")
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(8, 6, 8, 6)
            item_layout.setSpacing(2)
            name_label = QLabel(nome)
            name_label.setObjectName("viewerMaterialName")
            name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            item_layout.addWidget(name_label)
            source = textura.name if textura else "Cor sólida"
            source_label = QLabel(source)
            source_label.setObjectName("viewerMaterialSource")
            source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            item_layout.addWidget(source_label)
            self.materials_layout.addWidget(item)
        self.materials_layout.addStretch(1)

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
        self.stat_values["format"].setText(path.suffix.upper().lstrip(".") or "—")
        for key in ("resolution", "vertices", "triangles", "materials", "textures"):
            self.stat_values[key].setText("—")
        self._show_materials([])
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
        self._abrindo = True
        QTimer.singleShot(2000, self, self._desistir_de_insistir)
        self.show()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event) -> None:  # noqa: N802
        """Desfaz uma minimização que NÃO foi o Rafael que pediu.

        Medido: em 1 de 3 aberturas seguidas o gerenciador minimizava esta
        janela logo depois de ela aparecer — provavelmente porque a janela
        principal ainda estava assentando a própria maximização (a janela do
        visualizador é filha dela). Intermitente é pior que sempre quebrado:
        some quando se vai investigar e volta na hora que ele usa.

        A rede vale só nos 2s seguintes ao pedido de abrir. Depois disso,
        minimizar é vontade dele e não se discute.
        """
        if (event.type() == QEvent.Type.WindowStateChange
                and self._abrindo and self.isMinimized()):
            log.info("O gerenciador minimizou o visualizador na abertura — "
                     "desfazendo.")
            self.setWindowState(
                self.windowState() & ~Qt.WindowState.WindowMinimized)
            self.raise_()
            self.activateWindow()
        super().changeEvent(event)

    def _desistir_de_insistir(self) -> None:
        import shiboken6
        if not shiboken6.isValid(self):
            return
        self._abrindo = False

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
        self.stat_values["resolution"].setText(
            f"{imagem.width()} × {imagem.height()} px")
        self.materials_heading.setVisible(False)
        self.status.setText(
            f"{imagem.width()} × {imagem.height()} px  ·  "
            "arraste para girar, duplo clique centraliza")

    def _modelo_carregado(self, prepared: model_viewer.PreparedModel) -> None:
        malha = prepared.mesh
        log.info("Modelo pronto na tela: %s (%d vértices)",
                 getattr(self._alvo, "name", "?"), len(malha.positions))
        self.modelo.set_mesh(malha, buffer=prepared.buffer, images=prepared.images)
        n_tris = (len(malha.indices) if malha.indices is not None
                  else len(malha.positions)) // 3
        n_texturas = len({r.texture for r in malha.materials if r.texture is not None})
        materials = []
        vistos = set()
        for material in malha.materials:
            chave = (material.name, str(material.texture) if material.texture else None,
                     material.color)
            if chave not in vistos:
                vistos.add(chave)
                materials.append(material)
        self.stat_values["vertices"].setText(f"{len(malha.positions):,}".replace(",", "."))
        self.stat_values["triangles"].setText(f"{n_tris:,}".replace(",", "."))
        self.stat_values["materials"].setText(str(len(materials)))
        self.stat_values["textures"].setText(str(n_texturas))
        self._show_materials(materials)
        info_textura = f"  ·  {n_texturas} textura(s)" if n_texturas else ""
        self.status.setText(
            f"{n_tris:n} triângulos{info_textura}  ·  arraste para orbitar, roda pra zoom")

    def _falhou(self, mensagem: str) -> None:
        log.error("Visualizador não conseguiu abrir %s: %s",
                  getattr(self._alvo, "name", "?"), mensagem)
        self.status.setText(f"Não consegui abrir: {mensagem}")
        self._show_materials([])
        for key in self.stat_values:
            if key != "format":
                self.stat_values[key].setText("—")

    def _enquadrar(self) -> None:
        self.modelo.enquadrar()

    # ---- tema ----

    def refresh_theme(self) -> None:
        """Ícones tingidos à mão (não passam pelo QSS) e os cantos do palco,
        que são pintados com a cor de fundo do tema — mesmo padrão do
        seletor de biblioteca e das seções do painel de detalhes."""
        cores = theme.current_colors()
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
