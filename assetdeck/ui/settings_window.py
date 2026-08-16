"""Janela única de configurações/ferramentas (Fatia 67), acessada pelo
ícone de engrenagem na barra de menus — substitui os 5 menus de topo
(Arquivo/Editar/Ferramentas/Configurações/Janela). Pedido do Rafael:
"todas as opções numa janela só", com categorias numa lateral (mockup
aprovado por ele antes de programar).

Não-modal (`setModal(False)`): dá pra deixar aberta enquanto mexe na
janela principal — importante pros toggles de painel/filtro, onde o
Rafael quer ver o efeito na hora, sem fechar a janela pra cada clique.

Os botões/checkboxes daqui são atribuídos DIRETO na `MainWindow` (`mw.x =
...`), não guardados só aqui dentro: é o jeito mais simples de manter
todo o código que já lia `self.group_check`/`self.render_action`/etc.
funcionando sem mudar uma linha — a Fatia 43 já tinha usado o mesmo
truque trocando QCheckBox por QAction (a API `isChecked()`/`setChecked()`/
`toggled` é idêntica); aqui é o caminho inverso, QAction/QMenu vira
QPushButton/QCheckBox comuns.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsWindow(QDialog):
    def __init__(self, mw, parent=None) -> None:
        super().__init__(parent)
        self._mw = mw
        self.setWindowTitle("Configurações")
        self.setModal(False)
        self.resize(760, 480)

        self._lista = QListWidget()
        self._lista.setFixedWidth(170)
        self._paginas = QStackedWidget()

        categorias = [
            ("Ferramentas", self._pagina_ferramentas),
            ("Blender", self._pagina_blender),
            ("Preferências", self._pagina_preferencias),
            ("Aparência", self._pagina_aparencia),
            ("Painéis e filtros", self._pagina_paineis),
            ("Geral", self._pagina_geral),
        ]
        for nome, builder in categorias:
            self._lista.addItem(nome)
            self._paginas.addWidget(builder())
        self._lista.setCurrentRow(0)
        self._lista.currentRowChanged.connect(self._paginas.setCurrentIndex)

        layout = QHBoxLayout(self)
        layout.addWidget(self._lista)
        layout.addWidget(self._paginas, stretch=1)

    @staticmethod
    def _pagina(titulo: str) -> tuple[QWidget, QVBoxLayout]:
        pagina = QWidget()
        lay = QVBoxLayout(pagina)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("title")
        lay.addWidget(rotulo)
        return pagina, lay

    # ---- categorias ----

    def _pagina_ferramentas(self) -> QWidget:
        pagina, lay = self._pagina("Ferramentas")
        mw = self._mw
        mw.relocate_action = QPushButton("Relocalizar assets perdidos…")
        mw.relocate_action.clicked.connect(mw._relocate_lost_assets)
        mw.duplicates_action = QPushButton("Duplicados por conteúdo visual…")
        mw.duplicates_action.clicked.connect(mw._find_duplicates)
        btn_template = QPushButton("Aplicar template de tags…")
        btn_template.clicked.connect(mw.tags.apply_template_dialog)
        btn_previews = QPushButton("Assinalar previews automaticamente por nome agora")
        btn_previews.clicked.connect(mw._assinalar_previews_automaticamente)
        btn_props = QPushButton("Propriedades customizadas…")
        btn_props.clicked.connect(mw._manage_properties)
        for b in (mw.relocate_action, mw.duplicates_action, btn_template,
                  btn_previews, btn_props):
            lay.addWidget(b)
        lay.addStretch(1)
        return pagina

    def _pagina_blender(self) -> QWidget:
        pagina, lay = self._pagina("Blender")
        mw = self._mw
        btn_addon = QPushButton("Instalar / atualizar add-on…")
        btn_addon.clicked.connect(mw._install_addon)
        mw.render_action = QPushButton("Gerar capas dos modelos (render)…")
        mw.render_action.clicked.connect(mw._start_render)
        mw.cancel_render_action = QPushButton("Parar geração de capas")
        mw.cancel_render_action.clicked.connect(mw._stop_render)
        mw.cancel_render_action.setEnabled(False)
        btn_ajuda = QPushButton("Como usar")
        btn_ajuda.clicked.connect(mw._bridge_help)
        for b in (btn_addon, mw.render_action, mw.cancel_render_action, btn_ajuda):
            lay.addWidget(b)
        lay.addStretch(1)
        return pagina

    def _pagina_preferencias(self) -> QWidget:
        pagina, lay = self._pagina("Preferências")
        aviso = QLabel(
            "Ponte com o Blender, backups, geração automática de preview e "
            "a cena usada pra renderizar capas."
        )
        aviso.setWordWrap(True)
        btn = QPushButton("Abrir preferências…")
        btn.clicked.connect(self._mw._open_preferences)
        lay.addWidget(aviso)
        lay.addWidget(btn)
        lay.addStretch(1)
        return pagina

    def _pagina_aparencia(self) -> QWidget:
        from assetdeck import config

        pagina, lay = self._pagina("Aparência")
        mw = self._mw
        mw.dark_mode_action = QCheckBox("Modo escuro")
        mw.dark_mode_action.setChecked(config.load_config().get("theme_mode") == "escuro")
        mw.dark_mode_action.toggled.connect(mw._toggle_dark_mode)
        lay.addWidget(mw.dark_mode_action)
        lay.addStretch(1)
        return pagina

    def _pagina_paineis(self) -> QWidget:
        pagina, lay = self._pagina("Painéis e filtros")
        mw = self._mw

        mw._secoes_do_menu = [
            ("pastas", "Pastas"),
            ("tags", "Tags"),
            ("colecoes", "Coleções"),
            ("smart", "Smart Collections"),
        ]
        mw._panel_toggles = [
            (mw.sidebar.section_widget(chave), rotulo)
            for chave, rotulo in mw._secoes_do_menu
        ] + [(mw.details, "Painel de detalhes")]

        mw._window_menu_actions = []
        mw._acoes_por_secao: dict[str, object] = {}
        chaves = [chave for chave, _r in mw._secoes_do_menu] + [None]
        for chave, (widget, rotulo) in zip(chaves, mw._panel_toggles):
            check = QCheckBox(rotulo)
            check.setChecked(True)
            if chave is None:
                check.toggled.connect(widget.setVisible)
            else:
                check.toggled.connect(
                    lambda visivel, k=chave: mw.sidebar.set_section_visible(k, visivel)
                )
                mw._acoes_por_secao[chave] = check
            mw._window_menu_actions.append(check)
            lay.addWidget(check)

        # Rail → aqui: sem isto, desligar uma seção pelo ícone deixaria o
        # checkbox marcado, mentindo sobre o estado.
        mw.sidebar.rail.section_toggled.connect(mw._on_secao_alternada_pelo_rail)

        lay.addSpacing(4)

        mw.group_check = QCheckBox("Agrupar PBR")
        mw.group_check.setChecked(True)
        mw.group_check.toggled.connect(
            lambda c: (mw.model.set_expand_sets(not c), mw.refresh_count())
        )
        lay.addWidget(mw.group_check)

        mw.fav_check = QCheckBox("Só favoritos")
        mw.fav_check.setToolTip("Mostrar só favoritos")
        mw.fav_check.toggled.connect(lambda _c: mw._apply_filters())
        lay.addWidget(mw.fav_check)

        mw.deps_check = QCheckBox("Mostrar dependências")
        mw.deps_check.setToolTip(
            "Texturas que acompanham um .blend/.fbx irmão (mapas de um material\n"
            "convertido, texturas de um modelo). Desmarcado, você vê só o .blend."
        )
        mw.deps_check.toggled.connect(lambda _c: mw._apply_filters())
        lay.addWidget(mw.deps_check)

        mw.hidden_check = QCheckBox("Mostrar ocultos")
        mw.hidden_check.setToolTip(
            "Inclui imagens ocultadas por terem virado preview de um modelo"
        )
        mw.hidden_check.toggled.connect(lambda _c: mw._apply_filters())
        lay.addWidget(mw.hidden_check)

        lay.addSpacing(4)
        btn_restaurar = QPushButton("Restaurar layout padrão")
        btn_restaurar.clicked.connect(mw._restaurar_layout)
        lay.addWidget(btn_restaurar)

        lay.addStretch(1)
        return pagina

    def _pagina_geral(self) -> QWidget:
        pagina, lay = self._pagina("Geral")
        mw = self._mw
        btn_config = QPushButton("Abrir pasta de configuração")
        btn_config.clicked.connect(mw._abrir_pasta_config)
        btn_logs = QPushButton("Abrir pasta de logs")
        btn_logs.clicked.connect(mw._abrir_pasta_logs)
        btn_sair = QPushButton("Sair do AssetDeck")
        btn_sair.clicked.connect(mw.close)
        lay.addWidget(btn_config)
        lay.addWidget(btn_logs)
        lay.addSpacing(8)
        lay.addWidget(btn_sair)
        lay.addStretch(1)
        return pagina
