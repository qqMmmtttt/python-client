from typing import Any, Optional

from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.planning.estimates import estimate_delivery_rounds
from lychee_basic_client.planning.tasks import TASK_CUTOFF_ROUND, TASK_SCORE_GOAL
from lychee_basic_client.protocol.actions import claim_resource, use_resource
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.rules.buffs import has_move_buff
from lychee_basic_client.rules.states import NODE_BUSY_STATES, ROUTE_EDGE_STATES
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.speed_priority import should_prioritize_wuguan

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
    """资源策略：决定何时领取资源、何时使用马/冰鉴/情报等道具。"""

    def __init__(self, route_policy: Any = None) -> None:
        self._route_policy = route_policy
        self._attempted_pickups: set[tuple[str, str]] = set()
        self._used_intel_targets: set[str] = set()
        self._logger = get_logger("strategies.resources")

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
            # 路线边只允许使用马类资源；若前方有敌方设卡，主车队动作让位给设卡处理。
            if _has_adjacent_route_edge_guard(state, player):
                return []
            return _horse_action_if_useful(
                state,
                player,
                hold_for_t06=not _speed_priority_race(state, player, self._route_policy),
            )

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
            self._logger.important(
                "use_ice_box round=%s node=%s fresh=%s | 使用冰鉴：鲜度低于阈值，使用冰鉴将鲜度 +10（上限 100）以保鲜货物",
                state.round_no,
                player.current_node_id,
                player.freshness,
            )
            return [use_resource("ICE_BOX")]

        speed_race = _speed_priority_race(state, player, self._route_policy)

        # 速度优先段：马类资源用于压缩到武关的时间；其他 profile 下会保留马给
        # T06 等高价值任务窗口，避免提前浪费。
        horse_action = (
            []
            if _is_unprocessed_transfer_node(state)
            else _horse_action_if_useful(state, player, hold_for_t06=not speed_race)
        )
        if speed_race and horse_action:
            self._logger.important(
                "use_horse_speed_priority round=%s node=%s resource=%s"
                " | 速度优先：武关竞速段立即使用马类资源，优先压缩到达 S10 的时间",
                state.round_no,
                player.current_node_id,
                horse_action[0].get("resourceType"),
            )
            return horse_action

        if not speed_race and not _has_active_task_at_current_node(state, player.current_node_id):
            intel_action = _intel_action_if_useful(context, player, self._used_intel_targets)
            if intel_action:
                self._logger.important(
                    "use_intel round=%s from=%s target=%s | 使用情报：为目标节点添加己方探路标记，后续该节点处理帧数 -3",
                    state.round_no,
                    player.current_node_id,
                    intel_action[0].get("targetNodeId"),
                )
                return intel_action

        if horse_action:
            self._logger.important(
                "use_horse round=%s node=%s resource=%s | 使用马类资源：提升基础每帧移动量加速路线移动（快马 1200 / 短程马 1150）",
                state.round_no,
                player.current_node_id,
                horse_action[0].get("resourceType"),
            )
            return horse_action

        if player.current_node_id and state.round_no < 330 and _delivery_still_safe(
            state, player.current_node_id, margin=55
        ):
            node = state.nodes.get(player.current_node_id)
            if node:
                # 资源领取按“对当前策略价值”排序；领取动作是 main 类别，会和移动、
                # 破关等动作冲突，所以必须先确认交付时间仍安全。
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
                        and _should_claim_resource(
                            state,
                            player,
                            resource_type,
                            speed_race=speed_race,
                        )
                    ):
                        self._attempted_pickups.add(key)
                        self._logger.important(
                            "claim_resource round=%s node=%s resource=%s stock=%s | 领取资源：在资源点提交 CLAIM_RESOURCE 领取资源（2 帧处理）",
                            state.round_no,
                            player.current_node_id,
                            resource_type,
                            node.resource_stock.get(resource_type, 0),
                        )
                        return [claim_resource(player.current_node_id, resource_type)]
        return []


def _horse_action_if_useful(
    state: Any,
    player: Any,
    *,
    hold_for_t06: bool = True,
) -> list[dict[str, Any]]:
    hold_horse_for_t06 = (
        hold_for_t06
        and state.round_no < TASK_CUTOFF_ROUND
        and player.task_score < TASK_SCORE_GOAL
        and _has_active_t06(state)
    )
    if hold_horse_for_t06 or has_move_buff(player.raw):
        return []

    for resource_type in HORSE_RESOURCES:
        if player.resources.get(resource_type, 0) > 0:
            return [use_resource(resource_type)]
    return []


def _has_adjacent_route_edge_guard(state: Any, player: Any) -> bool:
    if not player.current_node_id:
        return False
    for node_id in state.game_map.neighbors(player.current_node_id):
        if enemy_guard_at(state.nodes.get(node_id), player) is not None:
            return True
    return False


def _has_active_t06(state: Any) -> bool:
    for task in state.tasks:
        if str(task.get("taskTemplateId") or "") != "T06":
            continue
        if task.get("active", True) and not task.get("completed") and not task.get("failed"):
            return True
    return False


def _has_active_task_at_current_node(state: Any, current_node_id: Optional[str]) -> bool:
    if not current_node_id:
        return False
    for task in state.tasks:
        if str(task.get("nodeId") or "") != current_node_id:
            continue
        if task.get("active", True) and not task.get("completed") and not task.get("failed"):
            return True
    return False


def _ice_box_threshold(state: Any) -> float:
    if state.phase == "RUSH" or state.weather.has_active("HOT"):
        return 84
    return 72


def _should_claim_resource(
    state: Any,
    player: Any,
    resource_type: str,
    *,
    speed_race: bool = False,
) -> bool:
    if player.resources.get(resource_type, 0) >= RESOURCE_TARGET_STOCK.get(resource_type, 1):
        return False
    if speed_race and resource_type not in {"FAST_HORSE", "SHORT_HORSE", "ICE_BOX"}:
        return False
    if speed_race and resource_type == "ICE_BOX" and player.freshness >= 82 and not state.weather.has_active("HOT"):
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
    route_distance = state.game_map.route_distance(current_node_id, target_node_id)
    if route_distance is None:
        return False
    return route_distance <= INTEL_RANGE_LIMIT


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


def _speed_priority_race(state: Any, player: Any, route_policy: Any) -> bool:
    return bool(
        player.current_node_id
        and should_prioritize_wuguan(route_policy, state, player.current_node_id)
    )


def _delivery_still_safe(state: Any, current_node_id: str, margin: int) -> bool:
    player = state.me
    if player is None:
        return False
    return state.round_no + estimate_delivery_rounds(state, current_node_id, player.verified) + margin < 600
