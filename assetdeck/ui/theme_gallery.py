"""Vitrine do tema: uma janela para escolher a aparência na tela, não no papel.

Aberta por `python -m assetdeck --theme-preview`. NÃO toca no app: existe para
o Rafael comparar as variantes ao vivo (fundo liso x com grão, três níveis de
translucidez, dois raios de canto, Inter x fonte do sistema) e apontar qual
combinação vai valer.

Mostra uma amostra de cada widget que o AssetDeck realmente usa — inclusive os
chatos, como o popup do QComboBox e o menu de contexto, que são janelas
separadas e não herdam o fundo dos painéis.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from assetdeck.ui import theme

log = logging.getLogger(__name__)

# (rótulo na tela, valor do Variant) para cada eixo de escolha
OPCOES = {
    "background": [("Liso", "liso"), ("Com grão de papel", "grao")],
    "translucency": [("Sutil", "sutil"), ("Média", "media"), ("Forte", "forte")],
    "radius": [("Discretos (12px)", "discreto"), ("Marcantes (18px)", "marcante")],
    "font": [("Inter", "inter"), ("Padrão do sistema", "sistema")],
}


class ThemeGallery(QWidget):
    """Janela única com os controles de variante e as amostras de widget."""

    def __init__(self, variant: theme.Variant | None = None) -> None:
        super().__init__()
        self.variant = variant or theme.DEFAULT

        # Subclasse de QWidget IGNORA background do QSS sem este atributo.
        # Foi medido: sem ele o #appSurface não pinta e o fundo fica cinza.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("appSurface")
        self.setWindowTitle("AssetDeck — vitrine do tema")
        self.resize(1180, 760)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 16, 16, 16)
        raiz.setSpacing(14)

        self._combos: dict[str, QComboBox] = {}
        raiz.addWidget(self._build_controls())

        corpo = QHBoxLayout()
        corpo.setSpacing(14)
        corpo.addWidget(theme.make_card(self._build_controls_sample(), titulo="Controles"), 1)
        corpo.addWidget(theme.make_card(self._build_lists_sample(), titulo="Painéis laterais"), 1)
        corpo.addWidget(theme.make_card(self._build_palette_sample(), titulo="Cores e texto"), 1)
        raiz.addLayout(corpo, 1)

        self.rodape = QLabel()
        self.rodape.setObjectName("muted")
        raiz.addWidget(self.rodape)

        self._apply()

    # ------------------------------------------------------------------ ui --

    def _build_controls(self) -> QWidget:
        """Barra de cima: os quatro eixos de escolha + recarregar."""
        barra = QWidget()
        linha = QHBoxLayout(barra)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(10)

        for campo, rotulo in (("background", "Fundo"), ("translucency", "Translucidez"),
                              ("radius", "Cantos"), ("font", "Fonte")):
            etiqueta = QLabel(rotulo)
            etiqueta.setObjectName("sectionTitle")
            linha.addWidget(etiqueta)

            combo = QComboBox()
            for texto, valor in OPCOES[campo]:
                combo.addItem(texto, valor)
            combo.setCurrentIndex(
                [v for _, v in OPCOES[campo]].index(getattr(self.variant, campo))
            )
            combo.currentIndexChanged.connect(self._on_variant_changed)
            self._combos[campo] = combo
            linha.addWidget(combo)

        linha.addStretch(1)

        recarregar = QPushButton("Recarregar tema")
        recarregar.setToolTip("Relê o theme.qss do disco sem fechar a janela.")
        recarregar.clicked.connect(self._apply)
        linha.addWidget(recarregar)
        return barra

    def _build_controls_sample(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(9)

        busca = QLineEdit()
        busca.setPlaceholderText("Buscar assets")
        busca.setClearButtonEnabled(True)
        col.addWidget(busca)

        combo = QComboBox()
        combo.addItems(["Nota: todas", "★ 3 ou mais", "★ 4 ou mais", "★ 5"])
        col.addWidget(combo)

        tipos = QToolButton()
        tipos.setText("Tipos: todos  ▾")
        menu = QMenu(tipos)
        for nome in ("Texturas", "HDRIs", "Modelos", "LUTs"):
            acao = menu.addAction(nome)
            acao.setCheckable(True)
        menu.addSeparator()
        menu.addAction("Limpar")
        tipos.setMenu(menu)
        tipos.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        col.addWidget(tipos)

        for texto, marcado in (("Incluir subpastas", True), ("Agrupar sets PBR", True),
                               ("Mostrar ocultos", False)):
            chk = QCheckBox(texto)
            chk.setChecked(marcado)
            col.addWidget(chk)

        botoes = QHBoxLayout()
        principal = QPushButton("Reindexar")
        principal.setObjectName("primary")
        botoes.addWidget(principal)
        botoes.addWidget(QPushButton("Cancelar"))
        desabilitado = QPushButton("Indisponível")
        desabilitado.setEnabled(False)
        botoes.addWidget(desabilitado)
        col.addLayout(botoes)

        estrelas = QHBoxLayout()
        estrelas.setSpacing(2)
        for i in range(5):
            b = QPushButton("★" if i < 4 else "☆")
            b.setObjectName("ghost")
            b.setMaximumWidth(30)
            estrelas.addWidget(b)
        estrelas.addStretch(1)
        col.addLayout(estrelas)

        # Nenhuma fonte da máquina tem o glifo da estrela (conferido com
        # QRawFont): o Qt cai numa fonte substituta e o desenho sai torto e de
        # tamanho imprevisível. É exatamente o que a Fatia 26 resolve.
        nota = QLabel("↑ estrelas ainda são texto — viram ícone SVG na Fatia 26")
        nota.setObjectName("muted")
        nota.setWordWrap(True)
        col.addWidget(nota)

        barra = QProgressBar()
        barra.setRange(0, 100)
        barra.setValue(64)
        barra.setTextVisible(False)
        col.addWidget(barra)

        notas = QPlainTextEdit("Notas do asset…")
        notas.setMaximumHeight(70)
        col.addWidget(notas)
        col.addStretch(1)
        return w

    def _build_lists_sample(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(9)

        arvore = QTreeWidget()
        arvore.setHeaderHidden(True)
        raiz = QTreeWidgetItem(arvore, ["assetdeck-testlib"])
        for nome in ("Texturas", "HDRIs", "Modelos"):
            QTreeWidgetItem(raiz, [nome])
        arvore.expandAll()
        arvore.setCurrentItem(raiz.child(0))
        col.addWidget(arvore)

        tags = QTreeWidget()
        tags.setHeaderHidden(True)
        for nome, cor in (("madeira", "#7E9C6B"), ("tijolo", "#B07A5E"), ("metal", "#7E8DA0")):
            item = QTreeWidgetItem(tags, [nome])
            swatch = QPixmap(12, 12)
            swatch.fill(QColor(cor))
            item.setIcon(0, swatch)
        col.addWidget(tags)

        colecoes = QListWidget()
        colecoes.addItems(["(nenhuma aplicada)", "HDRIs com nota ≥ 4", "Projeto Casa X"])
        colecoes.setCurrentRow(1)
        col.addWidget(colecoes)
        return w

    def _build_palette_sample(self) -> QWidget:
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        titulo = QLabel("Wood_Oak_4K")
        titulo.setObjectName("title")
        col.addWidget(titulo)

        secundario = QLabel("Set PBR · 6 mapas · 4096 px · 42 MB")
        secundario.setObjectName("muted")
        col.addWidget(secundario)

        aviso = QLabel("3 assets selecionados — a edição vale para todos")
        aviso.setObjectName("multiWarn")
        aviso.setWordWrap(True)
        col.addWidget(aviso)

        erro = QLabel("2 arquivos sumiram do disco")
        erro.setObjectName("danger")
        col.addWidget(erro)

        col.addSpacing(6)
        rotulo = QLabel("TINTS POR TIPO DE ASSET")
        rotulo.setObjectName("sectionTitle")
        col.addWidget(rotulo)

        grade = QGridLayout()
        grade.setSpacing(6)
        for i, (tipo, cor) in enumerate(theme.TYPE_TINTS.items()):
            amostra = QLabel(tipo)
            amostra.setAlignment(Qt.AlignmentFlag.AlignCenter)
            amostra.setFixedHeight(30)
            # Exceção consciente à regra "nada de setStyleSheet fora do
            # theme.py": aqui a cor É o conteúdo sendo demonstrado, e ela vem
            # do próprio theme.TYPE_TINTS.
            amostra.setStyleSheet(
                f"background-color: {cor}; color: white;"
                f" border-radius: 8px; font-size: 11px;"
            )
            grade.addWidget(amostra, i // 3, i % 3)
        col.addLayout(grade)
        col.addStretch(1)
        return w

    # --------------------------------------------------------------- lógica --

    def _on_variant_changed(self) -> None:
        self.variant = theme.Variant(
            **{campo: combo.currentData() for campo, combo in self._combos.items()}
        )
        self._apply()

    def _apply(self) -> None:
        """Reaplica o tema à aplicação inteira, relendo o theme.qss do disco."""
        theme.apply_theme(QApplication.instance(), self.variant)

        superficie = theme.surface_solid(self.variant)
        contraste = theme.contrast_ratio(theme.TEXT, superficie)
        contraste_muted = theme.contrast_ratio(theme.TEXT_MUTED, superficie)
        self.rodape.setText(
            f"Painel sobre o fundo = {superficie}  ·  contraste do texto "
            f"{contraste:.1f}:1  ·  do texto secundário {contraste_muted:.1f}:1  ·  "
            f"Variant({self.variant.background}, {self.variant.translucency}, "
            f"{self.variant.radius}, {self.variant.font})"
        )
