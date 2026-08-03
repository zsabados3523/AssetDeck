"""Diálogo da Fatia 36: preferências que hoje só existiam dentro do
config.json, sem UI nenhuma (bridge_enabled, bridge_port, hide_preview_source,
backup_keep). Só regrava o config.json — nenhuma migration, nenhum toque na
biblioteca."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
)

from assetdeck import config

log = logging.getLogger(__name__)

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
        layout.addRow(aviso)
        layout.addRow(botoes)

    def _salvar(self) -> None:
        self._cfg["bridge_enabled"] = self.bridge_enabled.isChecked()
        self._cfg["bridge_port"] = self.bridge_port.value()
        self._cfg["hide_preview_source"] = _LABEL_ORIGEM[self.hide_preview_source.currentText()]
        self._cfg["backup_keep"] = self.backup_keep.value()
        config.save_config(self._cfg)
        log.info("Preferências salvas (Fatia 36).")
        self.accept()
