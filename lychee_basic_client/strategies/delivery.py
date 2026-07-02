from typing import Any, Optional

from lychee_basic_client.models.state import GameState
from lychee_basic_client.protocol.actions import (
    break_guard,
    clear,
    deliver,
    dock,
    forced_pass,
    move,
    process,
    verify_gate,
)

BUSY_STATES = {"MOVING", "PROCESSING", "CONTESTING", "RESTING", "FORCED_PASSING", "VERIFYING"}

PREFERRED_ROUTE = [
    "S01",
    "S02",
    "S03",
    "S07",
    "S09",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
    "S15",
]


class DeliveryStrategy:
    """End-to-end S14 verification and S15 delivery decisions."""

    def __init__(self) -> None:
        self._completed_process_nodes: set[str] = set()
        self._pending_process_node: Optional[str] = None

    def on_start(self, state: GameState) -> None:
        self._completed_process_nodes.clear()
        self._pending_process_node = None
        return None

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        self._observe_process_completion(state)

        player = state.me
        if player is None or player.delivered:
            return []
        if player.state in BUSY_STATES or player.current_process:
            return []
        if not player.current_node_id:
            return []

        current = player.current_node_id
        gate = state.game_map.gate_node_id
        terminal = state.game_map.terminal_node_ids[0]

        if current == terminal and player.verified and player.good_fruit > 0 and player.freshness > 0:
            return [deliver()]

        if current == gate:
            if not player.verified:
                if state.phase == "RUSH":
                    return [verify_gate(gate)]
                return []
            return [move(terminal)]

        process_action = self._process_action_if_needed(state, current)
        if process_action:
            return [process_action]

        target = gate if not player.verified else terminal
        next_node = self._next_hop(state, current, target)
        if next_node is None:
            return []

        blocking_action = self._blocking_action_if_needed(state, next_node)
        if blocking_action:
            return [blocking_action]

        return [move(next_node)]
        return []

    def _process_action_if_needed(
        self, state: GameState, current: str
    ) -> Optional[dict[str, Any]]:
        if current in self._completed_process_nodes:
            return None
        process_node = state.game_map.process_node(current)
        if process_node is None or process_node.process_type == "VERIFY":
            return None

        self._pending_process_node = current
        if process_node.process_type == "BOARD":
            return dock(current)
        return process(current)

    def _next_hop(self, state: GameState, current: str, target: str) -> Optional[str]:
        preferred = _preferred_next_hop(current, target, state.game_map.nodes.keys())
        if preferred and preferred in state.game_map.neighbors(current):
            return preferred

        path = state.game_map.fastest_path(current, target)
        if len(path) >= 2:
            return path[1]
        return None

    def _blocking_action_if_needed(
        self, state: GameState, target_node_id: str
    ) -> Optional[dict[str, Any]]:
        player = state.me
        if player is None:
            return None
        node = state.nodes.get(target_node_id)
        if node is None:
            return None

        if node.has_obstacle and player.good_fruit > 0:
            return clear(target_node_id)

        guard = node.guard or {}
        owner_team_id = guard.get("ownerTeamId")
        defense = int(guard.get("defense") or 0)
        if owner_team_id and owner_team_id != player.team_id and defense > 0:
            if player.good_fruit > 5 or player.bad_fruit > 0:
                return break_guard(
                    target_node_id,
                    good_fruit=1 if player.good_fruit > 5 else 0,
                    bad_fruit=1 if player.bad_fruit > 0 else 0,
                )
            return forced_pass(target_node_id)
        return None

    def _observe_process_completion(self, state: GameState) -> None:
        player = state.me
        if player is None:
            return

        for event in state.events:
            if event.get("type") != "PROCESS_COMPLETE":
                continue
            payload = event.get("payload") or {}
            if payload.get("playerId") != state.player_id:
                continue
            node_id = payload.get("nodeId") or payload.get("targetNodeId") or self._pending_process_node
            if node_id:
                self._completed_process_nodes.add(node_id)
                if self._pending_process_node == node_id:
                    self._pending_process_node = None

        if (
            self._pending_process_node
            and player.state == "IDLE"
            and not player.current_process
            and player.current_node_id == self._pending_process_node
        ):
            self._completed_process_nodes.add(self._pending_process_node)
            self._pending_process_node = None


def _preferred_next_hop(current: str, target: str, available_nodes: Any) -> Optional[str]:
    available = set(available_nodes)
    if not all(node in available for node in PREFERRED_ROUTE):
        return None
    if current not in PREFERRED_ROUTE or target not in PREFERRED_ROUTE:
        return None
    current_index = PREFERRED_ROUTE.index(current)
    target_index = PREFERRED_ROUTE.index(target)
    if current_index >= target_index:
        return None
    return PREFERRED_ROUTE[current_index + 1]
