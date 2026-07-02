from typing import Any

from lychee_basic_client.planning.estimates import estimate_delivery_rounds
from lychee_basic_client.planning.tasks import TASK_SCORE_GOAL
from lychee_basic_client.protocol.actions import claim_resource, use_resource
from lychee_basic_client.strategies.context import StrategyContext

USEFUL_PICKUPS = ("FAST_HORSE", "SHORT_HORSE", "ICE_BOX")
BUSY_STATES = {"PROCESSING", "CONTESTING", "RESTING", "FORCED_PASSING", "VERIFYING"}


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
        if player is None or player.delivered or player.state in BUSY_STATES:
            return []

        if player.freshness and player.freshness < 75 and player.resources.get("ICE_BOX", 0) > 0:
            return [use_resource("ICE_BOX")]

        if player.state in {"IDLE", "MOVING", "WAITING"}:
            hold_horse_for_t06 = player.task_score < TASK_SCORE_GOAL and _has_active_t06(state)
            if (
                player.resources.get("FAST_HORSE", 0) > 0
                and not hold_horse_for_t06
                and not _has_move_buff(player.raw)
            ):
                return [use_resource("FAST_HORSE")]
            if (
                player.resources.get("SHORT_HORSE", 0) > 0
                and not hold_horse_for_t06
                and not _has_move_buff(player.raw)
            ):
                return [use_resource("SHORT_HORSE")]

        if (
            player.state == "IDLE"
            and player.current_node_id
            and state.round_no < 330
            and _delivery_still_safe(state, player.current_node_id)
        ):
            node = state.nodes.get(player.current_node_id)
            if node:
                for resource_type in USEFUL_PICKUPS:
                    key = (player.current_node_id, resource_type)
                    if node.resource_stock.get(resource_type, 0) > 0 and key not in self._attempted_pickups:
                        self._attempted_pickups.add(key)
                        return [claim_resource(player.current_node_id, resource_type)]
        return []


def _has_move_buff(raw_player: dict[str, Any]) -> bool:
    for buff in raw_player.get("buffs") or []:
        if buff.get("type") in {"FAST_HORSE", "SHORT_HORSE", "RUSH_SPEED"}:
            return True
    return False


def _has_active_t06(state: Any) -> bool:
    for task in state.tasks:
        if str(task.get("taskTemplateId") or "") != "T06":
            continue
        if task.get("active", True) and not task.get("completed") and not task.get("failed"):
            return True
    return False


def _delivery_still_safe(state: Any, current_node_id: str) -> bool:
    player = state.me
    if player is None:
        return False
    return state.round_no + estimate_delivery_rounds(state, current_node_id, player.verified) + 55 < 600
