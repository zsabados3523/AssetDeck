"""Servidor da ponte: QTcpServer assíncrono, só em 127.0.0.1.

Assíncrono de propósito: as respostas são SELECTs rápidos e rodam na thread
da UI sem travá-la — e assim a conexão SQLite não cruza threads.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

from assetdeck.bridge import handlers
from assetdeck.bridge import protocol as proto

log = logging.getLogger(__name__)


class BridgeServer(QObject):
    """Escuta comandos do add-on do Blender."""

    client_connected = Signal()
    client_disconnected = Signal()
    command_handled = Signal(str)  # nome do comando (para a barra de status)

    def __init__(self, conn: sqlite3.Connection, library_root: Path, token: str,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._library_root = library_root
        self._token = token
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._buffers: dict[QTcpSocket, bytearray] = {}

    # ---- ciclo de vida ----

    def start(self, port: int = proto.DEFAULT_PORT) -> bool:
        """Sobe o servidor. Retorna False (com log) se a porta estiver ocupada."""
        if self._server.isListening():
            return True
        # QHostAddress.LocalHost = 127.0.0.1: nunca aceita conexão de fora
        if not self._server.listen(QHostAddress(QHostAddress.SpecialAddress.LocalHost),
                                   port):
            log.error("Ponte não pôde escutar em 127.0.0.1:%d — %s",
                      port, self._server.errorString())
            return False
        log.info("Ponte do Blender ouvindo em 127.0.0.1:%d", port)
        return True

    def stop(self) -> None:
        for sock in list(self._buffers):
            sock.disconnectFromHost()
        self._buffers.clear()
        if self._server.isListening():
            self._server.close()
            log.info("Ponte do Blender encerrada.")

    @property
    def listening(self) -> bool:
        return self._server.isListening()

    @property
    def port(self) -> int:
        return self._server.serverPort()

    # ---- conexões ----

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._buffers[sock] = bytearray()
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(lambda s=sock: self._on_disconnected(s))
            log.info("Blender conectou à ponte.")
            self.client_connected.emit()

    def _on_disconnected(self, sock: QTcpSocket) -> None:
        self._buffers.pop(sock, None)
        sock.deleteLater()
        log.info("Blender desconectou da ponte.")
        self.client_disconnected.emit()

    def _on_ready_read(self, sock: QTcpSocket) -> None:
        buf = self._buffers.get(sock)
        if buf is None:
            return
        buf.extend(bytes(sock.readAll()))
        if len(buf) > proto.MAX_MESSAGE_BYTES:
            log.error("Mensagem grande demais na ponte — derrubando conexão.")
            sock.disconnectFromHost()
            return

        while b"\n" in buf:
            linha, _, resto = bytes(buf).partition(b"\n")
            buf.clear()
            buf.extend(resto)
            if linha.strip():
                sock.write(proto.encode(self._process(linha)))

    def _process(self, linha: bytes) -> dict:
        try:
            req = proto.decode(linha)
        except (ValueError, UnicodeDecodeError) as exc:
            log.warning("Mensagem inválida na ponte: %s", exc)
            return proto.error(f"JSON inválido: {exc}", code="bad_json")

        if req.get("token") != self._token:
            log.warning("Ponte recusou conexão com token inválido.")
            return proto.error(
                "Token inválido. Reinstale o add-on pelo AssetDeck "
                "(menu Blender → Instalar/atualizar add-on).",
                code="bad_token",
            )

        resposta = handlers.handle(self._conn, self._library_root, req)
        self.command_handled.emit(str(req.get("cmd")))
        return resposta
