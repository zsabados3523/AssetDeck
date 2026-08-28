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

**Fatia 80 (Fase 7, Etapa 2):** cada opção deixou de ser um botão
esticado de ponta a ponta e virou uma LINHA — título, uma frase dizendo
o que faz, e o controle à direita. Antes "Assinalar previews
automaticamente por nome agora" era um botão de 460px sem explicação
nenhuma. As categorias também mudaram (mockup aprovado): "Ferramentas"
virou "Manutenção", "Geral" virou "Sistema", "Painéis e filtros" se
partiu em dois — são perguntas diferentes ("quais painéis aparecem" e "o
que a grade mostra") — e a página "Preferências", cujo único conteúdo era
um botão que abria OUTRA janela, deixou de existir: o conteúdo dela se
distribuiu entre Blender e Sistema.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from assetdeck.ui import icons, theme

# Reaproveita o mapa que já existia em `preferences_dialog` — "ask" pergunta
# toda vez, "always"/"never" lembram a escolha (Fatia 10b). Importado de lá,
# não copiado: duas cópias divergiriam no dia que um rótulo mudasse.
from assetdeck.ui.preferences_dialog import _LABEL_ORIGEM, _ORIGEM_LABEL

_ORIGEM_ROTULOS = list(_ORIGEM_LABEL.values())
_ORIGEM_VALORES = _LABEL_ORIGEM


def _linha(titulo: str, descricao: str, controle: QWidget) -> QWidget:
    """Uma opção: texto à esquerda, controle à direita (Fatia 80).

    A descrição não é enfeite — é o que faltava. Um botão sozinho chamado
    "Assinalar previews automaticamente por nome agora" não diz o que vai
    acontecer com a biblioteca quando for clicado.
    """
    linha = QWidget()
    linha.setObjectName("cfgRow")
    linha.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lay = QHBoxLayout(linha)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(14)

    textos = QVBoxLayout()
    textos.setContentsMargins(0, 0, 0, 0)
    textos.setSpacing(1)
    rot = QLabel(titulo)
    rot.setObjectName("cfgTitulo")
    textos.addWidget(rot)
    if descricao:
        sub = QLabel(descricao)
        sub.setObjectName("cfgDesc")
        sub.setWordWrap(True)
        textos.addWidget(sub)
    lay.addLayout(textos, 1)
    lay.addWidget(controle, 0, Qt.AlignmentFlag.AlignVCenter)
    return linha


def _grupo(texto: str) -> QLabel:
    rot = QLabel(texto.upper())
    rot.setObjectName("cfgGrupo")
    return rot


class SettingsWindow(QDialog):
    def __init__(self, mw, parent=None) -> None:
        super().__init__(parent)
        self._mw = mw
        self.setWindowTitle("Configurações")
        self.setModal(False)
        self.resize(780, 520)

        self._lista = QListWidget()
        self._lista.setObjectName("cfgLista")
        self._lista.setFixedWidth(186)
        self._paginas = QStackedWidget()

        # (rótulo, ícone, construtor). O ícone é tingido à mão, então a
        # lista é reconstruída em `refresh_theme()` quando o modo troca.
        self._categorias = [
            ("Manutenção", "refresh", self._pagina_manutencao),
            ("Blender", "cat-modelos", self._pagina_blender),
            ("Aparência", "palette", self._pagina_aparencia),
            ("Painéis", "nav-pastas", self._pagina_paineis),
            ("Filtros", "filter", self._pagina_filtros),
            ("Sistema", "settings", self._pagina_sistema),
        ]
        for nome, icone, builder in self._categorias:
            item = QListWidgetItem(nome)
            item.setIcon(icons.icon(icone, theme.current_colors()["text_muted"], 15))
            self._lista.addItem(item)
            self._paginas.addWidget(self._rolavel(builder()))
        self._lista.setCurrentRow(0)
        self._lista.currentRowChanged.connect(self._paginas.setCurrentIndex)

        layout = QHBoxLayout(self)
        layout.addWidget(self._lista)
        layout.addWidget(self._paginas, stretch=1)

    def refresh_theme(self) -> None:
        """Reaplica os ícones da lateral na cor do modo atual (Fatia 80) —
        eles são tingidos em Python e não passam pelo QSS."""
        cor = theme.current_colors()["text_muted"]
        for i, (_nome, icone, _b) in enumerate(self._categorias):
            item = self._lista.item(i)
            if item is not None:
                item.setIcon(icons.icon(icone, cor, 15))

    # ---- montagem ----

    @staticmethod
    def _rolavel(pagina: QWidget) -> QWidget:
        """Cada página rola por conta própria: as de Painéis e Filtros já
        passam da altura da janela quando a biblioteca tem muitas seções."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(pagina)
        return scroll

    @staticmethod
    def _pagina(titulo: str, descricao: str = "") -> tuple[QWidget, QVBoxLayout]:
        pagina = QWidget()
        lay = QVBoxLayout(pagina)
        lay.setContentsMargins(18, 16, 18, 18)
        lay.setSpacing(4)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("title")
        lay.addWidget(rotulo)
        if descricao:
            sub = QLabel(descricao)
            sub.setObjectName("cfgDesc")
            sub.setWordWrap(True)
            lay.addWidget(sub)
        lay.addSpacing(8)
        return pagina, lay

    def _salvar(self, chave: str, valor) -> None:
        """Grava uma chave do config na hora (Fatia 80).

        A janela é NÃO-MODAL: não existe "OK/Cancelar" aqui, então cada
        controle aplica ao mudar — que é como os toggles de painel/filtro já
        se comportavam antes desta fatia.
        """
        from assetdeck import config

        cfg = config.load_config()
        cfg[chave] = valor
        config.save_config(cfg)

    # ---- categorias ----

    def _pagina_manutencao(self) -> QWidget:
        pagina, lay = self._pagina(
            "Manutenção", "Operações que varrem a biblioteca inteira.")
        mw = self._mw

        from assetdeck import config

        cfg = config.load_config()
        self.scan_on_startup = QCheckBox()
        self.scan_on_startup.setChecked(bool(cfg.get("scan_on_startup", False)))
        self.scan_on_startup.toggled.connect(
            lambda v: self._salvar("scan_on_startup", v))

        mw.relocate_action = QPushButton("Abrir…")
        mw.relocate_action.clicked.connect(mw._relocate_lost_assets)
        btn_esquecer = QPushButton("Esquecer…")
        btn_esquecer.clicked.connect(mw._esquecer_assets_sumidos)
        mw.duplicates_action = QPushButton("Procurar…")
        mw.duplicates_action.clicked.connect(mw._find_duplicates)
        btn_template = QPushButton("Aplicar…")
        btn_template.clicked.connect(mw.tags.apply_template_dialog)
        btn_previews = QPushButton("Rodar agora")
        btn_previews.clicked.connect(mw._assinalar_previews_automaticamente)
        btn_props = QPushButton("Gerenciar…")
        btn_props.clicked.connect(mw._manage_properties)

        lay.addWidget(_grupo("Varredura"))
        lay.addWidget(_linha(
            "Varrer a biblioteca ao abrir",
            "Desligado, a biblioteca só é lida quando você clicar em "
            "Reindexar. Ligado, o app varre tudo a cada abertura — numa "
            "biblioteca grande isso ocupa a máquina por alguns minutos.",
            self.scan_on_startup))

        lay.addWidget(_grupo("Arquivos"))
        lay.addWidget(_linha(
            "Relocalizar assets perdidos",
            "Religa no banco os arquivos que mudaram de pasta.",
            mw.relocate_action))
        lay.addWidget(_linha(
            "Esquecer assets sumidos",
            "Tira da grade os assets 100% ausentes (você moveu ou apagou "
            "fora do AssetDeck). Não mexe no disco, só no que é mostrado.",
            btn_esquecer))
        lay.addWidget(_linha(
            "Duplicados por conteúdo visual",
            "Acha imagens iguais mesmo com nomes diferentes.",
            mw.duplicates_action))

        lay.addWidget(_grupo("Organização"))
        lay.addWidget(_linha(
            "Template de tags",
            "Aplica um conjunto pronto de tags à biblioteca.",
            btn_template))
        lay.addWidget(_linha(
            "Assinalar previews por nome",
            "Casa imagem e modelo que tenham o mesmo nome.",
            btn_previews))
        lay.addWidget(_linha(
            "Propriedades customizadas",
            "Campos seus — fabricante, coleção, o que precisar.",
            btn_props))
        lay.addStretch(1)
        return pagina

    def _pagina_blender(self) -> QWidget:
        from assetdeck import config

        pagina, lay = self._pagina("Blender", "Ponte, add-on e geração de capas.")
        mw = self._mw
        cfg = config.load_config()

        btn_addon = QPushButton("Instalar…")
        btn_addon.clicked.connect(mw._install_addon)
        btn_ajuda = QPushButton("Como usar")
        btn_ajuda.clicked.connect(mw._bridge_help)
        mw.render_action = QPushButton("Gerar…")
        mw.render_action.setObjectName("primary")
        mw.render_action.clicked.connect(mw._start_render)
        mw.cancel_render_action = QPushButton("Parar")
        mw.cancel_render_action.clicked.connect(mw._stop_render)
        mw.cancel_render_action.setEnabled(False)
        btn_cena = QPushButton("Ajustar…")
        btn_cena.clicked.connect(mw._open_preferences)

        # Vindos da antiga janela de Preferências (Fatia 80).
        self.bridge_enabled = QCheckBox()
        self.bridge_enabled.setChecked(bool(cfg.get("bridge_enabled", True)))
        self.bridge_enabled.toggled.connect(
            lambda v: self._salvar("bridge_enabled", v))
        self.bridge_port = QSpinBox()
        self.bridge_port.setRange(1024, 65535)
        self.bridge_port.setValue(int(cfg.get("bridge_port", 45017)))
        self.bridge_port.valueChanged.connect(
            lambda v: self._salvar("bridge_port", v))

        lay.addWidget(_grupo("Conexão"))
        lay.addWidget(_linha(
            "Ponte com o Blender",
            "Vale depois de reabrir o AssetDeck.",
            self.bridge_enabled))
        lay.addWidget(_linha("Porta da ponte", "", self.bridge_port))
        lay.addWidget(_linha(
            "Add-on no Blender",
            "Instala ou atualiza o add-on que recebe os assets.",
            btn_addon))
        lay.addWidget(_linha("Como a ponte funciona", "", btn_ajuda))

        lay.addWidget(_grupo("Capas dos modelos"))
        lay.addWidget(_linha(
            "Gerar capas (render)",
            "Renderiza uma prévia de cada modelo que ainda não tem.",
            mw.render_action))
        lay.addWidget(_linha(
            "Interromper geração", "", mw.cancel_render_action))
        lay.addWidget(_linha(
            "Cena do render",
            "Cor do fundo, força do fundo e intensidade do sol.",
            btn_cena))
        lay.addStretch(1)
        return pagina

    def _pagina_aparencia(self) -> QWidget:
        from assetdeck import config

        pagina, lay = self._pagina("Aparência", "Como o AssetDeck se apresenta.")
        mw = self._mw
        mw.dark_mode_action = QCheckBox()
        mw.dark_mode_action.setChecked(
            config.load_config().get("theme_mode") == "escuro")
        mw.dark_mode_action.toggled.connect(mw._toggle_dark_mode)

        lay.addWidget(_grupo("Tema"))
        lay.addWidget(_linha(
            "Modo escuro",
            "Vale na hora, sem reabrir o app.",
            mw.dark_mode_action))
        lay.addStretch(1)
        return pagina

    def _pagina_paineis(self) -> QWidget:
        pagina, lay = self._pagina(
            "Painéis", "Quais partes da janela ficam visíveis.")
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

        lay.addWidget(_grupo("Lateral"))
        for chave, (widget, rotulo) in zip(chaves, mw._panel_toggles):
            check = QCheckBox()
            check.setChecked(True)
            if chave is None:
                check.toggled.connect(widget.setVisible)
                lay.addWidget(_grupo("Direita"))
            else:
                check.toggled.connect(
                    lambda visivel, k=chave: mw.sidebar.set_section_visible(k, visivel)
                )
                mw._acoes_por_secao[chave] = check
            mw._window_menu_actions.append(check)
            lay.addWidget(_linha(rotulo, "", check))

        # Rail → aqui: sem isto, desligar uma seção pelo ícone deixaria o
        # checkbox marcado, mentindo sobre o estado.
        mw.sidebar.rail.section_toggled.connect(mw._on_secao_alternada_pelo_rail)

        btn_restaurar = QPushButton("Restaurar")
        btn_restaurar.clicked.connect(mw._restaurar_layout)
        lay.addWidget(_grupo("Layout"))
        lay.addWidget(_linha(
            "Restaurar layout padrão",
            "Volta tamanhos, painéis e divisórias ao original.",
            btn_restaurar))
        lay.addStretch(1)
        return pagina

    def _pagina_filtros(self) -> QWidget:
        from assetdeck import config

        pagina, lay = self._pagina(
            "Filtros", "O que a grade mostra por padrão.")
        mw = self._mw
        cfg = config.load_config()

        mw.group_check = QCheckBox()
        mw.group_check.setChecked(True)
        mw.group_check.toggled.connect(
            lambda c: (mw.model.set_expand_sets(not c), mw.refresh_count())
        )
        mw.fav_check = QCheckBox()
        mw.fav_check.toggled.connect(lambda _c: mw._apply_filters())
        mw.deps_check = QCheckBox()
        mw.deps_check.toggled.connect(lambda _c: mw._apply_filters())
        mw.hidden_check = QCheckBox()
        mw.hidden_check.toggled.connect(lambda _c: mw._apply_filters())
        mw.missing_check = QCheckBox()
        mw.missing_check.toggled.connect(lambda _c: mw._apply_filters())

        lay.addWidget(_grupo("O que aparece na grade"))
        lay.addWidget(_linha(
            "Agrupar PBR",
            "Um set de texturas conta como um card só.",
            mw.group_check))
        lay.addWidget(_linha(
            "Só favoritos", "Esconde tudo que não está marcado.", mw.fav_check))
        lay.addWidget(_linha(
            "Mostrar dependências",
            "Texturas que acompanham um .blend/.fbx irmão.",
            mw.deps_check))
        lay.addWidget(_linha(
            "Mostrar assets sumidos",
            "Arquivos que a varredura não achou mais no disco. Ligue pra "
            "usar Manutenção → Relocalizar, que religa o que só mudou de "
            "pasta.",
            mw.missing_check))
        lay.addWidget(_linha(
            "Mostrar ocultos",
            "Inclui imagens ocultadas por virarem preview de um modelo.",
            mw.hidden_check))

        # Vindos da antiga janela de Preferências (Fatia 80).
        self.auto_match_previews = QCheckBox()
        self.auto_match_previews.setChecked(
            bool(cfg.get("auto_match_previews_by_name", False)))
        self.auto_match_previews.toggled.connect(self._on_auto_match)

        self.auto_match_hide_source = QCheckBox()
        self.auto_match_hide_source.setChecked(
            bool(cfg.get("auto_match_hide_source", False)))
        # Só faz sentido com o de cima ligado — ocultar a origem de um
        # casamento que não acontece não quer dizer nada.
        self.auto_match_hide_source.setEnabled(self.auto_match_previews.isChecked())
        self.auto_match_hide_source.toggled.connect(
            lambda v: self._salvar("auto_match_hide_source", v))

        self.hide_preview_source = QComboBox()
        for rotulo in _ORIGEM_ROTULOS:
            self.hide_preview_source.addItem(rotulo)
        atual = cfg.get("hide_preview_source", "ask")
        self.hide_preview_source.setCurrentText(
            {v: k for k, v in _ORIGEM_VALORES.items()}.get(atual, _ORIGEM_ROTULOS[0]))
        self.hide_preview_source.currentTextChanged.connect(
            lambda t: self._salvar("hide_preview_source", _ORIGEM_VALORES[t]))

        lay.addWidget(_grupo("Previews automáticos"))
        lay.addWidget(_linha(
            "Assinalar previews por nome igual",
            "Toda varredura casa imagem e modelo de mesmo nome.",
            self.auto_match_previews))
        lay.addWidget(_linha(
            "Ocultar a imagem usada como preview",
            "Some da grade a imagem que virou capa de um modelo.",
            self.auto_match_hide_source))
        lay.addWidget(_linha(
            "Ao usar imagem da biblioteca como preview",
            "O que fazer com a imagem de origem.",
            self.hide_preview_source))
        lay.addStretch(1)
        return pagina

    def _on_auto_match(self, ligado: bool) -> None:
        self._salvar("auto_match_previews_by_name", ligado)
        self.auto_match_hide_source.setEnabled(ligado)

    def _pagina_sistema(self) -> QWidget:
        from assetdeck import config

        pagina, lay = self._pagina(
            "Sistema", "Onde o AssetDeck guarda as coisas.")
        mw = self._mw
        cfg = config.load_config()

        btn_config = QPushButton("Abrir")
        btn_config.clicked.connect(mw._abrir_pasta_config)
        btn_logs = QPushButton("Abrir")
        btn_logs.clicked.connect(mw._abrir_pasta_logs)

        lay.addWidget(_grupo("Pastas"))
        lay.addWidget(_linha(
            "Configuração", str(config.config_dir()), btn_config))
        lay.addWidget(_linha("Logs", str(config.logs_dir()), btn_logs))

        # Vindo da antiga janela de Preferências (Fatia 80).
        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(1, 90)
        self.backup_keep.setValue(int(cfg.get("backup_keep", 14)))
        self.backup_keep.setSuffix(" dias")
        self.backup_keep.valueChanged.connect(
            lambda v: self._salvar("backup_keep", v))

        lay.addWidget(_grupo("Backups do banco"))
        lay.addWidget(_linha(
            "Manter backups diários",
            "Um por dia; os mais antigos são apagados.",
            self.backup_keep))

        btn_sair = QPushButton("Sair")
        btn_sair.setObjectName("danger")
        btn_sair.clicked.connect(mw.close)
        # Zona própria (Fatia 80): antes "Sair do AssetDeck" ficava encostado
        # em "Abrir pasta de logs" — a ação que fecha o app não devia dividir
        # bloco com um utilitário.
        rot_risco = _grupo("Zona de risco")
        rot_risco.setObjectName("cfgGrupoRisco")
        lay.addWidget(rot_risco)
        lay.addWidget(_linha(
            "Sair do AssetDeck",
            "Fecha o app. O estado da janela é salvo antes.",
            btn_sair))
        lay.addStretch(1)
        return pagina
