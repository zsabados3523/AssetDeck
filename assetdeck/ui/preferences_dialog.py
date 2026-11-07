"""Diálogo da Fatia 36: preferências que hoje só existiam dentro do
config.json, sem UI nenhuma (bridge_enabled, bridge_port, hide_preview_source,
backup_keep). Só regrava o config.json — nenhuma migration, nenhum toque na
biblioteca."""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
)

from assetdeck import config
from assetdeck.ui import dialog_chrome

log = logging.getLogger(__name__)


def _amostra_de_cor(hex_color: str, tam: int = 18):
    """Ícone de cor sólida pro botão — nunca setStyleSheet (regra do
    projeto: cor nova é ícone/token, não QSS solto). Mesmo padrão do
    quadradinho de cor de tag (`ui/tag_icons.py::_quadradinho`)."""
    from PySide6.QtGui import QIcon, QPixmap

    pix = QPixmap(tam, tam)
    pix.fill(QColor(hex_color))
    return QIcon(pix)


# hide_preview_source (Fatia 10b): "ask" pergunta toda vez, "always"/"never"
# lembram a escolha — ver _on_asset_preview_dropped em main_window.py.
_ORIGEM_LABEL = {
    "ask": "Perguntar sempre",
    "always": "Sempre ocultar a origem",
    "never": "Nunca ocultar a origem",
}
_LABEL_ORIGEM = {v: k for k, v in _ORIGEM_LABEL.items()}


class PreferencesDialog(QDialog):
    """Editor da CENA DE RENDER das capas (Fatia 38) e preferências gerais."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Cena do render"))

        self._cfg = config.load_config()

        # Cena de render de capas (Fatia 38) — vale na próxima vez que
        # clicar em "Gerar capas", sem precisar reabrir o app.
        self._render_bg_color = self._cfg.get("render_bg_color", "#959599")
        self.render_bg_color_btn = QPushButton(self.tr("Escolher…"))
        self.render_bg_color_btn.setIcon(_amostra_de_cor(self._render_bg_color))
        self.render_bg_color_btn.clicked.connect(self._escolher_cor_luz_ambiente)

        self.render_bg_strength = QDoubleSpinBox()
        self.render_bg_strength.setRange(0.1, 10.0)
        self.render_bg_strength.setSingleStep(0.1)
        self.render_bg_strength.setValue(float(self._cfg.get("render_bg_strength", 1.8)))

        self.render_sun_energy = QDoubleSpinBox()
        self.render_sun_energy.setRange(0.1, 20.0)
        self.render_sun_energy.setSingleStep(0.5)
        self.render_sun_energy.setValue(float(self._cfg.get("render_sun_energy", 3.0)))

        # Seletor de idioma (GitHub issue #18)
        self.language_combo = QComboBox()
        self.language_combo.addItem("Português", "pt_BR")
        self.language_combo.addItem("English", "en")
        current_lang = str(self._cfg.get("language") or "").lower()
        if current_lang.startswith("en"):
            self.language_combo.setCurrentIndex(1)
        else:
            self.language_combo.setCurrentIndex(0)

        aviso = QLabel(
            self.tr("Vale na próxima vez que gerar capas — não precisa reabrir o app.")
        )
        aviso.setWordWrap(True)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        dialog_chrome.prepare_actions(botoes)

        layout = QFormLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        dialog_chrome.add_heading(
            layout, self.tr("Iluminação das capas"),
            self.tr("Ajuste as luzes usadas na próxima geração de capas."))
        # Fatia 102: o fundo é sempre transparente agora — estes três
        # campos afinam a ILUMINAÇÃO, não mais um fundo visível.
        layout.addRow(self.tr("Cor da luz ambiente:"), self.render_bg_color_btn)
        layout.addRow(self.tr("Intensidade da luz ambiente:"), self.render_bg_strength)
        layout.addRow(self.tr("Intensidade da luz principal:"), self.render_sun_energy)
        layout.addRow(self.tr("Idioma:"), self.language_combo)
        layout.addRow(aviso)
        layout.addRow(botoes)

    def _escolher_cor_luz_ambiente(self) -> None:
        cor = QColorDialog.getColor(QColor(self._render_bg_color), self,
                                    self.tr("Cor da luz ambiente"))
        if cor.isValid():
            self._render_bg_color = cor.name()
            self.render_bg_color_btn.setIcon(_amostra_de_cor(self._render_bg_color))

    def _salvar(self) -> None:
        self._cfg["render_bg_color"] = self._render_bg_color
        self._cfg["render_bg_strength"] = self.render_bg_strength.value()
        self._cfg["render_sun_energy"] = self.render_sun_energy.value()
        self._cfg["language"] = self.language_combo.currentData()
        config.save_config(self._cfg)
        log.info("Preferências salvas (Fatia 36).")
        self.accept()
