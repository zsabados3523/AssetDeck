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
    """Editor da CENA DE RENDER das capas (Fatia 38).

    Era a janela de "Preferências" inteira. Na Fatia 80 (Fase 7, Etapa 2)
    tudo que era liga/desliga simples — ponte com o Blender, porta, backups,
    previews automáticos — saiu daqui e virou LINHA na janela de
    Configurações, onde aplica na hora. Sobrou o que de fato é um formulário
    de vários campos que só faz sentido confirmar junto: cor do fundo, força
    do fundo e intensidade do sol. Por isso continua modal, com OK/Cancelar.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cena do render")

        self._cfg = config.load_config()

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
            "Vale na próxima vez que gerar capas — não precisa reabrir o app."
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
        self._cfg["render_bg_color"] = self._render_bg_color
        self._cfg["render_bg_strength"] = self.render_bg_strength.value()
        self._cfg["render_sun_energy"] = self.render_sun_energy.value()
        config.save_config(self._cfg)
        log.info("Preferências salvas (Fatia 36).")
        self.accept()
