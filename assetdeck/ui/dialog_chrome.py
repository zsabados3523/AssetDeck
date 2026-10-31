"""Peças comuns para cabeçalho e faixa de ações dos diálogos."""

from PySide6.QtWidgets import QDialogButtonBox, QLabel, QWidget


def add_heading(layout, title: str, description: str = "") -> tuple[QLabel, QLabel | None]:
    """Insere um título interno e uma descrição com nomes QSS partilhados."""
    heading = QLabel(title)
    heading.setObjectName("dialogHeading")
    _insert(layout, heading)

    subtitle = None
    if description:
        subtitle = QLabel(description)
        subtitle.setObjectName("dialogDescription")
        subtitle.setWordWrap(True)
        _insert(layout, subtitle)
    return heading, subtitle


def _insert(layout, widget: QWidget) -> None:
    """Insere em layouts de formulário ou verticais sem impor um tipo."""
    add_row = getattr(layout, "addRow", None)
    if callable(add_row):
        add_row(widget)
    else:
        layout.addWidget(widget)


def prepare_actions(buttons: QDialogButtonBox) -> QDialogButtonBox:
    """Dá a cada caixa de ações o mesmo separador e espaçamento visual."""
    buttons.setObjectName("dialogActions")
    return buttons
