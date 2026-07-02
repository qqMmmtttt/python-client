import socket
from typing import Any, Iterable

from lychee_basic_client.protocol.framing import read_frame, write_frame


class ScriptedMockServer:
    """Small socketpair-based server helper for session smoke tests."""

    def __init__(self, server_sock: socket.socket, outbound_messages: Iterable[dict[str, Any]]) -> None:
        self._server_sock = server_sock
        self._outbound_messages = list(outbound_messages)
        self.received: list[dict[str, Any]] = []

    def run(self) -> None:
        try:
            self.received.append(read_frame(self._server_sock))
            for message in self._outbound_messages:
                write_frame(self._server_sock, message)
                self.received.append(read_frame(self._server_sock))
        finally:
            self._server_sock.close()

