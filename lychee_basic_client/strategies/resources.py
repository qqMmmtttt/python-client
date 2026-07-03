from typing import Any

from lychee_basic_client.planning.estimates import estimate_delivery_rounds
from lychee_basic_client.planning.tasks import TASK_CUTOFF_ROUND, TASK_SCORE_GOAL
from lychee_basic_client.protocol.actions import claim_resource, use_resource
from lychee_basic_client.rules.buffs import has_move_buff
from lychee_basic_client.rules.states import NODE_BUSY_STATES, ROUTE_EDGE_STATES
from lychee_basic_client.strategies.context import StrategyContext

USEFUL_PICKUPS = (
    "ICE_BOX",
    "FAST_HORSE",
    "SHORT_HORSE",
    "PASS_TOKEN",
    "OFFICIAL_PERMIT",
    "INTEL",
    "BOAT_RIGHT",
)
HORSE_RESOURCES = ("FAST_HORSE", "SHORT_HORSE")
INTEL_TARGETS = ("S11", "S13", "S14", "S04", "S05")
INTEL_RANGE_LIMIT = 15
RESOURCE_TARGET_STOCK = {
    "ICE_BOX": 2,
    "FAST_HORSE": 1,
    "SHORT_HORSE": 1,
    "PASS_TOKEN": 1,
    "OFFICIAL_PERMIT": 1,
    "INTEL": 2,
    "BOAT_RIGHT": 1,
}
RESOURCE_PICKUP_MARGIN = {
    "ICE_BOX": 35,
    "FAST_HORSE": 38,
    "SHORT_HORSE": 34,
    "PASS_TOKEN": 32,
    "OFFICIAL_PERMIT": 32,
    "INTEL": 28,
    "BOAT_RIGHT": 18,
}


class ResourceStrategy:
    """Resource pickup and inventory-use decisions."""

    def __init__(self) -> None:
        self._attempted_pickups: set[tuple[str, str]] = set()
        self._used_intel_targets: set[str] = set()

    def on_start(self, state: Any) -> None:
        self._attempted_pickups.clear()
        self._used_intel_targets.clear()
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
            and player.freshness < _ice_box_threshold(state)
            and player.resources.get("ICE_BOX", 0) > 0
            and player.current_node_id
            and _delivery_still_safe(state, player.current_node_id, margin=25)
        ):
            return [use_resource("ICE_BOX")]

        intel_action = _intel_action_if_useful(context, player, self._used_intel_targets)
        if intel_action:
            return intel_action

        horse_action = [] if _is_unprocessed_transfer_node(state) else _horse_action_if_useful(state, player)
        if horse_action:
            return horse_action

        if player.current_node_id and state.round_no < 330 and _delivery_still_safe(
            state, player.current_node_id, margin=55
        ):
            node = state.nodes.get(player.current_node_id)
            if node:
                resource_types = sorted(
                    USEFUL_PICKUPS,
                    key=lambda item: _pickup_sort_key(state, player, item),
                    reverse=True,
                )
                for resource_type in resource_types:
                    key = (player.current_node_id, resource_type)
                    if (
                        node.resource_stock.get(resource_type, 0) > 0
                        and key not in self._attempted_pickups
                        and _should_claim_resource(state, player, resource_type)
                    ):
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


def _ice_box_threshold(state: Any) -> float:
    if state.phase == "RUSH" or state.weather.has_active("HOT"):
        return 84
    return 72


def _should_claim_resource(state: Any, player: Any, resource_type: str) -> bool:
    if player.resources.get(resource_type, 0) >= RESOURCE_TARGET_STOCK.get(resource_type, 1):
        return False
    if resource_type == "BOAT_RIGHT" and player.current_node_id != "S04":
        return False
    if resource_type in {"PASS_TOKEN", "OFFICIAL_PERMIT"} and _document_stock(player) >= 1:
        return False
    margin = RESOURCE_PICKUP_MARGIN.get(resource_type, 35)
    return bool(
        player.current_node_id
        and _delivery_still_safe(state, player.current_node_id, margin=margin)
    )


def _pickup_sort_key(state: Any, player: Any, resource_type: str) -> tuple[int, int]:
    if resource_type == "ICE_BOX":
        value = 100 if player.freshness < 85 or state.weather.has_active("HOT") else 82
    elif resource_type == "FAST_HORSE":
        value = 94
    elif resource_type == "SHORT_HORSE":
        value = 88
    elif resource_type == "INTEL":
        value = 78
    elif resource_type in {"PASS_TOKEN", "OFFICIAL_PERMIT"}:
        value = 72
    elif resource_type == "BOAT_RIGHT":
        value = 45
    else:
        value = 0
    if state.phase == "RUSH" and resource_type in {"PASS_TOKEN", "OFFICIAL_PERMIT"}:
        value += 10
    return (value, -RESOURCE_PICKUP_MARGIN.get(resource_type, 35))


def _document_stock(player: Any) -> int:
    return player.resources.get("PASS_TOKEN", 0) + player.resources.get("OFFICIAL_PERMIT", 0)


def _intel_action_if_useful(
    context: StrategyContext,
    player: Any,
    used_targets: set[str],
) -> list[dict[str, Any]]:
    state = context.state
    if player.resources.get("INTEL", 0) <= 0 or not player.current_node_id:
        return []
    if not _delivery_still_safe(state, player.current_node_id, margin=15):
        return []

    targets = _intel_targets_for_state(context, player.current_node_id)
    for target in targets:
        if target in used_targets:
            continue
        if target in state.game_map.terminal_node_ids:
            continue
        if target not in state.game_map.nodes:
            continue
        if not _within_intel_range(state, player.current_node_id, target):
            continue
        if _has_own_scout_marker(state, target):
            used_targets.add(target)
            continue
        used_targets.add(target)
        return [use_resource("INTEL", target)]
    return []


def _intel_targets_for_state(context: StrategyContext, current_node_id: str) -> list[str]:
    state = context.state
    targets: list[str] = []
    process_node = state.game_map.process_node(current_node_id)
    if (
        process_node is not None
        and process_node.process_type != "VERIFY"
        and current_node_id not in context.events.completed_process_nodes
    ):
        targets.append(current_node_id)
    targets.extend(INTEL_TARGETS)

    deduped: list[str] = []
    for target in targets:
        if target not in deduped:
            deduped.append(target)
    return deduped


def _within_intel_range(state: Any, current_node_id: str, target_node_id: str) -> bool:
    current = state.game_map.nodes.get(current_node_id)
    target = state.game_map.nodes.get(target_node_id)
    if current is None or target is None:
        return False
    current_x = int(current.raw.get("x") or 0)
    current_y = int(current.raw.get("y") or 0)
    target_x = int(target.raw.get("x") or 0)
    target_y = int(target.raw.get("y") or 0)
    return max(abs(current_x - target_x), abs(current_y - target_y)) <= INTEL_RANGE_LIMIT


def _has_own_scout_marker(state: Any, target_node_id: str) -> bool:
    player = state.me
    node = state.nodes.get(target_node_id)
    if player is None or node is None:
        return False
    markers = node.raw.get("scouted") or node.raw.get("scouts") or []
    for marker in markers:
        if marker.get("playerId") == state.player_id or marker.get("teamId") == player.team_id:
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
