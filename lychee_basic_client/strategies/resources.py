from typing import Any

from lychee_basic_client.planning.estimates import estimate_delivery_rounds
from lychee_basic_client.planning.tasks import TASK_CUTOFF_ROUND, TASK_SCORE_GOAL
from lychee_basic_client.protocol.actions import claim_resource, use_resource
from lychee_basic_client.rules.buffs import has_move_buff
from lychee_basic_client.rules.states import NODE_BUSY_STATES, ROUTE_EDGE_STATES
from lychee_basic_client.strategies.context import StrategyContext

USEFUL_PICKUPS = ("FAST_HORSE", "SHORT_HORSE", "ICE_BOX")
HORSE_RESOURCES = ("FAST_HORSE", "SHORT_HORSE")


class ResourceStrategy:
    """Resource pickup and inventory-use decisions."""

    def __init__(self) -> None:
        self._attempted_pickups: set[tuple[str, str]] = set()

    def on_start(self, state: Any) -> None:
        self._attempted_pickups.clear()
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None or player.delivered or player.state in NODE_BUSY_STATES:
            return []

        if player.state in ROUTE_EDGE_STATES:
            return _horse_action_if_useful(state, player)

        if player.state != "IDLE":
            return []

        if player.current_node_id in {state.game_map.gate_node_id, *state.game_map.terminal_node_ids}:
            return []

        if (
            player.freshness
            and player.freshness < 75
            and player.resources.get("ICE_BOX", 0) > 0
            and player.current_node_id
            and _delivery_still_safe(state, player.current_node_id, margin=25)
        ):
            return [use_resource("ICE_BOX")]

        horse_action = [] if _is_unprocessed_transfer_node(state) else _horse_action_if_useful(state, player)
        if horse_action:
            return horse_action

        if player.current_node_id and state.round_no < 330 and _delivery_still_safe(
            state, player.current_node_id, margin=55
        ):
            node = state.nodes.get(player.current_node_id)
            if node:
                for resource_type in USEFUL_PICKUPS:
                    key = (player.current_node_id, resource_type)
                    if node.resource_stock.get(resource_type, 0) > 0 and key not in self._attempted_pickups:
                        self._attempted_pickups.add(key)
                        return [claim_resource(player.current_node_id, resource_type)]
        return []


def _horse_action_if_useful(state: Any, player: Any) -> list[dict[str, Any]]:
    hold_horse_for_t06 = (
        state.round_no < TASK_CUTOFF_ROUND
        and player.task_score < TASK_SCORE_GOAL
        and _has_active_t06(state)
    )
    if hold_horse_for_t06 or has_move_buff(player.raw):
        return []

    for resource_type in HORSE_RESOURCES:
        if player.resources.get(resource_type, 0) > 0:
            return [use_resource(resource_type)]
    return []


def _has_active_t06(state: Any) -> bool:
    for task in state.tasks:
        if str(task.get("taskTemplateId") or "") != "T06":
            continue
        if task.get("active", True) and not task.get("completed") and not task.get("failed"):
            return True
    return False


def _is_unprocessed_transfer_node(state: Any) -> bool:
    player = state.me
    if player is None or not player.current_node_id:
        return False
    process_node = state.game_map.process_node(player.current_node_id)
    return process_node is not None and process_node.process_type != "VERIFY"


def _delivery_still_safe(state: Any, current_node_id: str, margin: int) -> bool:
    player = state.me
    if player is None:
        return False
    return state.round_no + estimate_delivery_rounds(state, current_node_id, player.verified) + margin < 600
