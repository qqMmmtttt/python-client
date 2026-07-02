from typing import Any, Optional

from lychee_basic_client.models.state import GameState
from lychee_basic_client.planning.tasks import find_t04_for_obstacle, select_task_target
from lychee_basic_client.protocol.actions import (
    break_guard,
    clear,
    deliver,
    dock,
    forced_pass,
    claim_task,
    move,
    process,
    verify_gate,
)
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.routing import RoutePolicy

BUSY_STATES = {"MOVING", "PROCESSING", "CONTESTING", "RESTING", "FORCED_PASSING", "VERIFYING"}


class DeliveryStrategy:
    """End-to-end S14 verification and S15 delivery decisions."""

    def __init__(self, route_policy: RoutePolicy) -> None:
        self._route_policy = route_policy
        self._completed_process_nodes: set[str] = set()
        self._pending_process_node: Optional[str] = None

    def on_start(self, state: GameState) -> None:
        self._completed_process_nodes.clear()
        self._pending_process_node = None
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        self._observe_process_completion(context)

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

        task_target = select_task_target(state, current)
        if task_target is not None and task_target.stand_node_id == current:
            return [claim_task(task_target.task_id)]
        target = task_target.stand_node_id if task_target is not None else gate
        if player.verified:
            target = terminal
        next_node = self._route_policy.next_hop(state, current, target)
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

    def _blocking_action_if_needed(
        self, state: GameState, target_node_id: str
    ) -> Optional[dict[str, Any]]:
        player = state.me
        if player is None:
            return None
        node = state.nodes.get(target_node_id)
        if node is None:
            return None

        if node.has_obstacle:
            t04 = find_t04_for_obstacle(state, target_node_id)
            if t04 is not None:
                return claim_task(t04["taskId"])
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

    def _observe_process_completion(self, context: StrategyContext) -> None:
        state = context.state
        player = state.me
        if player is None:
            return

        for node_id in context.events.completed_process_nodes:
            self._completed_process_nodes.add(node_id)
            if self._pending_process_node == node_id:
                self._pending_process_node = None

        for rejected in context.events.rejected_actions:
            if rejected.action in {"PROCESS", "DOCK"} and self._pending_process_node:
                self._pending_process_node = None
            if rejected.error_code == "PROCESS_REQUIRED" and player.current_node_id:
                self._completed_process_nodes.discard(player.current_node_id)
