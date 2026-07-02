import json
import socket
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.protocol.actions import action_message
from lychee_basic_client.protocol.framing import read_frame, write_frame
from lychee_basic_client.protocol.messages import ready_message, registration_message
from lychee_basic_client.strategies.factory import build_strategy


class ClientSession:
    def __init__(self, sock: socket.socket, config: Config) -> None:
        self._sock = sock
        self._config = config
        self._strategy = build_strategy(config)
        self._state: Optional[GameState] = None
        self._logger = get_logger("runtime.session")

    def run(self) -> int:
        self._send_registration()

        while True:
            try:
                message = read_frame(self._sock)
            except EOFError:
                self._logger.important("connection closed")
                return 0
            except Exception:
                self._logger.exception("failed to read server frame")
                return 1

            result = self._handle_message(message)
            if result is not None:
                return result

    def _send_registration(self) -> None:
        self._logger.important("sending registration player_id=%s", self._config.player_id)
        write_frame(self._sock, registration_message(self._config))

    def _handle_message(self, message: dict[str, Any]) -> Optional[int]:
        msg_name = message.get("msg_name")
        data = message.get("msg_data") or {}

        if msg_name == "start":
            self._handle_start(data)
        elif msg_name == "inquire":
            self._handle_inquire(data)
        elif msg_name == "over":
            self._logger.important("over received: %s", json.dumps(data, ensure_ascii=False))
            return 0
        elif msg_name == "error":
            self._logger.error("error received: %s", json.dumps(message, ensure_ascii=False))
            return 1
        else:
            self._logger.warning("ignored msg_name=%s", msg_name)
        return None

    def _handle_start(self, data: dict[str, Any]) -> None:
        self._state = GameState.from_start(data, self._config.player_id)
        self._strategy.on_start(self._state)
        self._logger.important(
            "start match=%s round=%s player_id=%s",
            self._state.match_id,
            self._state.round_no,
            self._config.player_id,
        )
        write_frame(
            self._sock,
            ready_message(self._state.match_id, self._state.round_no, self._config.player_id),
        )

    def _handle_inquire(self, data: dict[str, Any]) -> None:
        if self._state is None:
            self._logger.error("inquire received before start")
            return

        self._state = GameState.from_inquire(data, self._config.player_id, self._state.game_map)
        actions = self._strategy.decide(self._state)
        player = self._state.me
        self._logger.info(
            "round=%s phase=%s state=%s node=%s actions=%s",
            self._state.round_no,
            self._state.phase,
            player.state if player else None,
            player.current_node_id if player else None,
            actions,
        )
        write_frame(
            self._sock,
            action_message(
                self._state.match_id,
                self._state.round_no,
                self._config.player_id,
                actions,
            ),
        )

