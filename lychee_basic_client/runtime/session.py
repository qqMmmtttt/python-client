import json
import socket
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.protocol.actions import action_message
from lychee_basic_client.protocol.framing import encode_frame, read_frame_with_meta
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
                message, prefix, body = read_frame_with_meta(self._sock)
                self._log_wire("inbound", message, prefix, len(body))
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
        self._send_message(registration_message(self._config))

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
            if self._state is None:
                return 1
            return None
        else:
            self._logger.warning("ignored msg_name=%s", msg_name)
        return None

    def _handle_start(self, data: dict[str, Any]) -> None:
        self._state = GameState.from_start(data, self._config.player_id)
        self._strategy.on_start(self._state)
        self._logger.important(
            "start match=%s round=%s player_id=%s nodes=%s edges=%s process_nodes=%s tasks=%s",
            self._state.match_id,
            self._state.round_no,
            self._config.player_id,
            len(self._state.game_map.nodes),
            len(self._state.game_map.edges),
            sorted(self._state.game_map.process_nodes.keys()),
            _summarize_task_templates(data.get("taskTemplates") or []),
        )
        self._send_message(
            ready_message(self._state.match_id, self._state.round_no, self._config.player_id),
        )

    def _handle_inquire(self, data: dict[str, Any]) -> None:
        if self._state is None:
            self._logger.error("inquire received before start")
            return

        self._state = GameState.from_inquire(data, self._config.player_id, self._state.game_map)
        actions = self._strategy.decide(self._state)
        player = self._state.me
        self._logger.important(
            "round=%s phase=%s player_state=%s node=%s next=%s score=%s task_score=%s "
            "good=%s bad=%s fresh=%s weather=%s tasks=%s events=%s action_results=%s actions=%s",
            self._state.round_no,
            self._state.phase,
            player.state if player else None,
            player.current_node_id if player else None,
            player.next_node_id if player else None,
            player.total_score if player else None,
            player.task_score if player else None,
            player.good_fruit if player else None,
            player.bad_fruit if player else None,
            player.freshness if player else None,
            _summarize_weather(self._state.weather.raw),
            _summarize_tasks(self._state.tasks),
            _summarize_events(self._state.events),
            _summarize_action_results(self._state.action_results),
            actions,
        )
        self._logger.info(
            "round=%s phase=%s state=%s node=%s actions=%s",
            self._state.round_no,
            self._state.phase,
            player.state if player else None,
            player.current_node_id if player else None,
            actions,
        )
        self._send_message(
            action_message(
                self._state.match_id,
                self._state.round_no,
                self._config.player_id,
                actions,
            ),
        )

    def _send_message(self, message: dict[str, Any]) -> None:
        frame = encode_frame(message)
        self._log_wire("outbound", message, frame[:5], len(frame) - 5)
        self._sock.sendall(frame)

    def _log_wire(
        self,
        direction: str,
        message: dict[str, Any],
        prefix: bytes,
        body_length: int,
    ) -> None:
        data = message.get("msg_data") or {}
        self._logger.trace(
            "wire direction=%s msg_name=%s round=%s player_id=%s prefix=%s body_bytes=%s message=%s",
            direction,
            message.get("msg_name"),
            data.get("round"),
            data.get("playerId"),
            prefix.decode("ascii", errors="replace"),
            body_length,
            json.dumps(message, ensure_ascii=False, separators=(",", ":")),
        )


def _summarize_task_templates(task_templates: list[dict[str, Any]]) -> list[str]:
    return [
        f"{task.get('taskTemplateId')}:{task.get('score')}:{task.get('processRound')}"
        for task in task_templates
    ]


def _summarize_tasks(tasks: list[dict[str, Any]]) -> list[str]:
    summary = []
    for task in tasks:
        if task.get("completed") or task.get("failed") or not task.get("active", True):
            continue
        summary.append(
            "%s/%s@%s score=%s owner=%s protect=%s expire=%s"
            % (
                task.get("taskId"),
                task.get("taskTemplateId"),
                task.get("nodeId"),
                task.get("score"),
                task.get("ownerPlayerId"),
                task.get("protectionPlayerId"),
                task.get("expireRound"),
            )
        )
    return summary


def _summarize_weather(weather: dict[str, Any]) -> dict[str, Any]:
    return {
        "active": weather.get("active") or weather.get("current") or [],
        "forecast": weather.get("forecast") or weather.get("upcoming") or [],
    }


def _summarize_events(events: list[dict[str, Any]]) -> list[str]:
    summary = []
    important_types = {
        "TASK_REFRESH",
        "TASK_COMPLETE",
        "TASK_EXPIRE",
        "TASK_TARGET_LOST",
        "PROCESS_COMPLETE",
        "ACTION_REJECTED",
        "INVALID_ACTION",
        "WINDOW_CONTEST_START",
        "WINDOW_CONTEST_END",
        "WINDOW_CONTEST_DRAW",
        "RESOURCE_CLAIM",
        "RESOURCE_USE",
        "OBSTACLE_CLEAR",
        "GUARD_BREAK",
        "GUARD_INACTIVE",
        "GUARD_WEATHERING",
        "FORCED_PASS_START",
        "FORCED_PASS_END",
        "SQUAD_DISPATCH",
        "SQUAD_SCOUT",
        "SQUAD_CLEAR",
        "SQUAD_REINFORCE",
        "SQUAD_WEAKEN",
        "SQUAD_FAILED",
        "RUSH_START",
        "VERIFY_GATE_COMPLETE",
        "DELIVER_SUCCESS",
    }
    for event in events:
        event_type = event.get("type")
        if event_type not in important_types:
            continue
        payload = event.get("payload") or {}
        summary.append(
            "%s player=%s node=%s target=%s task=%s error=%s score=%s"
            % (
                event_type,
                payload.get("playerId"),
                payload.get("nodeId"),
                payload.get("targetNodeId"),
                payload.get("taskId"),
                payload.get("errorCode"),
                payload.get("score") or payload.get("scoreDelta"),
            )
        )
    return summary


def _summarize_action_results(action_results: list[dict[str, Any]]) -> list[str]:
    return [
        "%s player=%s accepted=%s result=%s error=%s"
        % (
            result.get("action"),
            result.get("playerId"),
            result.get("accepted"),
            result.get("result"),
            result.get("errorCode"),
        )
        for result in action_results
    ]
