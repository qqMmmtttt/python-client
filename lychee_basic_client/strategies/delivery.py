from typing import Any, Optional

from lychee_basic_client.models.state import GameState
from lychee_basic_client.planning.estimates import estimate_delivery_rounds
from lychee_basic_client.planning.tasks import find_t04_for_obstacle, select_task_target
from lychee_basic_client.protocol.actions import (
    break_guard,
    clear,
    deliver,
    forced_pass,
    claim_task,
    move,
    process,
    verify_gate,
)
from lychee_basic_client.rules.states import MAIN_ACTION_BUSY_STATES
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.routing import RoutePolicy


class DeliveryStrategy:
    """End-to-end S14 verification and S15 delivery decisions."""

    def __init__(self, route_policy: RoutePolicy) -> None:
        self._route_policy = route_policy
        self._completed_process_nodes: set[str] = set()
        self._pending_process_node: Optional[str] = None
        self._last_settled_node: Optional[str] = None
        self._rejected_task_ids: set[str] = set()

    def on_start(self, state: GameState) -> None:
        self._completed_process_nodes.clear()
        self._pending_process_node = None
        self._last_settled_node = None
        self._rejected_task_ids.clear()
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        self._observe_process_completion(context)

        player = state.me
        if player is None or player.delivered:
            return []
        if player.state in MAIN_ACTION_BUSY_STATES or player.current_process:
            return []
        if not player.current_node_id:
            return []

        current = player.current_node_id
        gate = state.game_map.gate_node_id
        terminal = state.game_map.terminal_node_ids[0]
        self._observe_new_settled_node(state, current)

        if current == terminal:
            if player.verified and player.good_fruit > 0 and player.freshness > 0:
                return [deliver()]
            if not player.verified:
                next_node = self._route_policy.next_hop(state, current, gate)
                return [move(next_node)] if next_node else []
            return []

        if current == gate:
            if not player.verified:
                if state.phase == "RUSH":
                    rush_tactic = "BREAK_ORDER" if _should_bind_break_order_to_verify(state) else None
                    return [verify_gate(gate, rush_tactic=rush_tactic)]
                return []
            return [move(terminal)]

        process_action = self._process_action_if_needed(state, current)
        if process_action:
            return [process_action]

        task_target = select_task_target(state, current, self._rejected_task_ids)
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

    def _process_action_if_needed(
        self, state: GameState, current: str
    ) -> Optional[dict[str, Any]]:
        if current in self._completed_process_nodes:
            return None
        process_node = state.game_map.process_node(current)
        if process_node is None or process_node.process_type == "VERIFY":
            return None

        self._pending_process_node = current
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
            t04 = find_t04_for_obstacle(state, target_node_id, self._rejected_task_ids)
            if t04 is not None:
                return claim_task(t04["taskId"])
        if node.has_obstacle:
            if player.good_fruit > 0 and _has_delivery_slack(state, target_node_id, margin=38):
                return clear(target_node_id)
            return forced_pass(target_node_id)

        guard = node.guard or {}
        owner_team_id = guard.get("ownerTeamId")
        defense = int(guard.get("defense") or 0)
        if owner_team_id and owner_team_id != player.team_id and defense > 0:
            if _has_delivery_slack(state, target_node_id, margin=30) and (
                player.good_fruit > 5 or player.bad_fruit > 0
            ):
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
            if rejected.action == "CLAIM_TASK":
                task_id = _rejected_task_id(rejected.raw)
                if task_id:
                    self._rejected_task_ids.add(task_id)

    def _observe_new_settled_node(self, state: GameState, current: str) -> None:
        if current == self._last_settled_node:
            return
        self._last_settled_node = current
        process_node = state.game_map.process_node(current)
        if process_node is not None and process_node.process_type != "VERIFY":
            self._completed_process_nodes.discard(current)


def _should_bind_break_order_to_verify(state: GameState) -> bool:
    player = state.me
    if player is None:
        return False
    if state.phase != "RUSH" or player.rush_tactic_used_count > 0:
        return False
    if player.bad_fruit >= 2:
        return True
    if player.good_fruit <= 1:
        return False
    return state.round_no + estimate_delivery_rounds(state, state.game_map.gate_node_id, False) >= 570


def _has_delivery_slack(state: GameState, from_node_id: str, margin: int) -> bool:
    player = state.me
    if player is None:
        return False
    return state.round_no + estimate_delivery_rounds(state, from_node_id, player.verified) + margin < 600


def _rejected_task_id(raw: dict[str, Any]) -> str:
    payload = raw.get("payload") or raw
    return str(payload.get("taskId") or "")
