"""Filtro de tipos em checklist multi-seleção (sugestão do Rafael).

Um botão que abre uma lista de checkboxes — marcar 'model' + 'texture'
mostra os dois tipos juntos. Clicar nos checkboxes NÃO fecha o menu.

Fatia 31: cada tipo marcado que tenha mais de uma extensão presente na
biblioteca ganha um checklist secundário indentado (ex.: 'model' com
.fbx/.obj/.blend) — só aparece enquanto o tipo pai estiver marcado.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)


class TypeFilter(QToolButton):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._checks: dict[str, QCheckBox] = {}
        self._ext_checks: dict[str, dict[str, QCheckBox]] = {}
        self._ext_containers: dict[str, QWidget] = {}
        self._update_label()

    def reload(self, types: list[str],
               extensions_by_type: dict[str, list[str]] | None = None) -> None:
        """Reconstrói o checklist preservando o que estava marcado
        (tipos e extensões). `extensions_by_type` vem de
        `assets_repo.distinct_extensions` por tipo — só ganha checklist de
        extensão o tipo com mais de uma presente na biblioteca."""
        extensions_by_type = extensions_by_type or {}
        marcados = set(self.selected())
        marcados_ext = {t: set(exts) for t, exts in self._ext_selection().items()}
        self._menu.clear()
        self._checks = {}
        self._ext_checks = {}
        self._ext_containers = {}

        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 8, 8, 8)
        for t in types:
            cb = QCheckBox(t)
            cb.setChecked(t in marcados)
            layout.addWidget(cb)
            self._checks[t] = cb

            exts = extensions_by_type.get(t, [])
            if len(exts) > 1:
                ext_box = QWidget()
                ext_layout = QVBoxLayout(ext_box)
                ext_layout.setContentsMargins(24, 0, 0, 0)
                ext_layout.setSpacing(2)
                self._ext_checks[t] = {}
                for e in exts:
                    ecb = QCheckBox(f".{e}")
                    ecb.setChecked(e in marcados_ext.get(t, set()))
                    ecb.toggled.connect(self._on_toggle)
                    ext_layout.addWidget(ecb)
                    self._ext_checks[t][e] = ecb
                ext_box.setVisible(cb.isChecked())
                self._ext_containers[t] = ext_box
                layout.addWidget(ext_box)
                cb.toggled.connect(lambda checked, box=ext_box: box.setVisible(checked))

            cb.toggled.connect(self._on_toggle)

        clear = QPushButton("Limpar (mostrar todos)")
        clear.clicked.connect(self._clear)
        layout.addWidget(clear)

        action = QWidgetAction(self._menu)
        action.setDefaultWidget(box)
        self._menu.addAction(action)
        self._update_label()

    def selected(self) -> list[str]:
        """Tipos marcados; lista vazia significa 'todos'."""
        return [t for t, cb in self._checks.items() if cb.isChecked()]

    def set_selected(self, types: list[str]) -> None:
        """Restaura uma seleção (ex.: ao aplicar uma Smart Collection salva).
        Não emite 'changed' — quem chama decide quando reaplicar o filtro."""
        alvo = set(types)
        for t, cb in self._checks.items():
            cb.blockSignals(True)
            cb.setChecked(t in alvo)
            cb.blockSignals(False)
            if t in self._ext_containers:
                self._ext_containers[t].setVisible(cb.isChecked())
        self._update_label()

    def selected_extensions(self) -> list[str]:
        """Extensões marcadas, só contando as de tipos atualmente marcados
        (uma extensão escondida por causa do tipo pai desmarcado não conta).
        Lista vazia = sem restrição de extensão."""
        exts: list[str] = []
        for t, ext_map in self._ext_checks.items():
            if not self._checks[t].isChecked():
                continue
            exts.extend(e for e, cb in ext_map.items() if cb.isChecked())
        return exts

    def set_selected_extensions(self, extensions: list[str]) -> None:
        """Restaura extensões marcadas (ex.: Smart Collection). Chamar DEPOIS
        de `set_selected`, senão o tipo pai pode ainda não estar marcado.
        Não emite 'changed'."""
        alvo = {e.lower() for e in extensions}
        for ext_map in self._ext_checks.values():
            for e, cb in ext_map.items():
                cb.blockSignals(True)
                cb.setChecked(e in alvo)
                cb.blockSignals(False)
        self._update_label()

    def _ext_selection(self) -> dict[str, list[str]]:
        """Snapshot cru (sem filtrar por tipo marcado) — usado só pra
        preservar o estado dos checkboxes através de um `reload`."""
        return {t: [e for e, cb in exts.items() if cb.isChecked()]
                for t, exts in self._ext_checks.items()}

    def _on_toggle(self, _checked: bool) -> None:
        self._update_label()
        self.changed.emit()

    def _clear(self) -> None:
        for cb in self._checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        for t, box in self._ext_containers.items():
            box.setVisible(False)
            for cb in self._ext_checks[t].values():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)
        self._update_label()
        self._menu.close()
        self.changed.emit()

    def _update_label(self) -> None:
        sel = self.selected() if self._checks else []
        if not sel:
            self.setText("Tipos: todos ▾")
            return
        texto = f"Tipo: {sel[0]}" if len(sel) == 1 else f"Tipos: {len(sel)} marcados"
        ext_sel = self.selected_extensions() if self._ext_checks else []
        if ext_sel:
            texto += f" ({len(ext_sel)} ext)"
        self.setText(f"{texto} ▾")
