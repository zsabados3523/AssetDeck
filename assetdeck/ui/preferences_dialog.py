"""Diálogo da Fatia 36: preferências que hoje só existiam dentro do
config.json, sem UI nenhuma (bridge_enabled, bridge_port, hide_preview_source,
backup_keep). Só regrava o config.json — nenhuma migration, nenhum toque na
biblioteca."""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
)

from assetdeck import config

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
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferências")

        self._cfg = config.load_config()

        self.bridge_enabled = QCheckBox("Ativar ponte com o Blender")
        self.bridge_enabled.setChecked(bool(self._cfg.get("bridge_enabled", True)))

        self.bridge_port = QSpinBox()
        self.bridge_port.setRange(1024, 65535)
        self.bridge_port.setValue(int(self._cfg.get("bridge_port", 45017)))

        self.hide_preview_source = QComboBox()
        self.hide_preview_source.addItems(list(_ORIGEM_LABEL.values()))
        atual = self._cfg.get("hide_preview_source", "ask")
        self.hide_preview_source.setCurrentText(_ORIGEM_LABEL.get(atual, _ORIGEM_LABEL["ask"]))

        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(1, 365)
        self.backup_keep.setValue(int(self._cfg.get("backup_keep", 14)))

        # Cena de render de capas (Fatia 38) — vale na próxima vez que
        # clicar em "Gerar capas", sem precisar reabrir o app.
        self._render_bg_color = self._cfg.get("render_bg_color", "#959599")
        self.render_bg_color_btn = QPushButton("Escolher…")
        self.render_bg_color_btn.setIcon(_amostra_de_cor(self._render_bg_color))
        self.render_bg_color_btn.clicked.connect(self._escolher_cor_fundo)

        self.render_bg_strength = QDoubleSpinBox()
        self.render_bg_strength.setRange(0.1, 10.0)
        self.render_bg_strength.setSingleStep(0.1)
        self.render_bg_strength.setValue(float(self._cfg.get("render_bg_strength", 1.8)))

        self.render_sun_energy = QDoubleSpinBox()
        self.render_sun_energy.setRange(0.1, 20.0)
        self.render_sun_energy.setSingleStep(0.5)
        self.render_sun_energy.setValue(float(self._cfg.get("render_sun_energy", 3.0)))

        aviso = QLabel(
            "Ativar/desativar a ponte e trocar a porta só valem depois de "
            "reabrir o AssetDeck."
        )
        aviso.setWordWrap(True)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addRow(self.bridge_enabled)
        layout.addRow("Porta da ponte:", self.bridge_port)
        layout.addRow("Imagem da biblioteca como preview:", self.hide_preview_source)
        layout.addRow("Backups diários a manter:", self.backup_keep)
        layout.addRow("Cor do fundo do render:", self.render_bg_color_btn)
        layout.addRow("Força do fundo:", self.render_bg_strength)
        layout.addRow("Intensidade do sol:", self.render_sun_energy)
        layout.addRow(aviso)
        layout.addRow(botoes)

    def _escolher_cor_fundo(self) -> None:
        cor = QColorDialog.getColor(QColor(self._render_bg_color), self,
                                    "Cor do fundo do render")
        if cor.isValid():
            self._render_bg_color = cor.name()
            self.render_bg_color_btn.setIcon(_amostra_de_cor(self._render_bg_color))

    def _salvar(self) -> None:
        self._cfg["bridge_enabled"] = self.bridge_enabled.isChecked()
        self._cfg["bridge_port"] = self.bridge_port.value()
        self._cfg["hide_preview_source"] = _LABEL_ORIGEM[self.hide_preview_source.currentText()]
        self._cfg["backup_keep"] = self.backup_keep.value()
        self._cfg["render_bg_color"] = self._render_bg_color
        self._cfg["render_bg_strength"] = self.render_bg_strength.value()
        self._cfg["render_sun_energy"] = self.render_sun_energy.value()
        config.save_config(self._cfg)
        log.info("Preferências salvas (Fatia 36).")
        self.accept()
