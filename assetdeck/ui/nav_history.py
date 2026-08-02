"""Pilha de navegação de pastas (Fatia 32).

Sem Qt de propósito: é lógica pura de navegador (voltar/avançar, com o
"futuro" descartado quando você navega a partir do meio), testável sem
instanciar widget nenhum.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class NavHistory:
    """Histórico linear de caminhos de pasta ('' = biblioteca inteira)."""

    def __init__(self, inicial: str = "") -> None:
        self._itens: list[str] = [inicial]
        self._pos = 0

    def current(self) -> str:
        return self._itens[self._pos]

    def push(self, prefix: str) -> None:
        """Navegou pra uma pasta nova. Igual a navegador: se havia 'futuro'
        (você tinha voltado), ele é descartado a partir daqui."""
        if prefix == self.current():
            return  # clicar de novo na mesma pasta não é navegação
        del self._itens[self._pos + 1:]
        self._itens.append(prefix)
        self._pos = len(self._itens) - 1

    def can_back(self) -> bool:
        return self._pos > 0

    def can_forward(self) -> bool:
        return self._pos < len(self._itens) - 1

    def back(self) -> str:
        if not self.can_back():
            raise IndexError("Nada pra voltar — checar can_back() antes.")
        self._pos -= 1
        return self.current()

    def forward(self) -> str:
        if not self.can_forward():
            raise IndexError("Nada pra avançar — checar can_forward() antes.")
        self._pos += 1
        return self.current()

    def replace_current(self, prefix: str) -> None:
        """Troca a entrada atual sem criar navegação nova — usado quando a
        pasta some do disco e caímos na raiz, pra o Voltar não devolver o
        usuário pra uma pasta que não existe mais."""
        self._itens[self._pos] = prefix
