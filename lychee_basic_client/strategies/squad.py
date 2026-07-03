import math
from typing import Any, Optional

from lychee_basic_client.protocol.actions import squad_clear, squad_scout, squad_weaken
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.rules.states import ROUTE_EDGE_STATES
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.routing import RoutePolicy
from lychee_basic_client.strategies.speed_priority import route_policy_is_speed_priority


SCOUT_TARGETS = ("S04", "S05", "S11", "S13", "S14")
CRITICAL_GUARD_CAPS = {
    "S10": 7,
    "S11": 7,
    "S14": 4,
}
SQUAD_WEAKEN_COST = 2
SQUAD_WEAKEN_VALUE = 2


class SquadStrategy:
    """Independent small-team actions that should not block the main convoy."""

    def __init__(self, route_policy: Optional[RoutePolicy] = None) -> None:
        self._route_policy = route_policy
        self._logger = get_logger("strategies.squad")
        self._dispatched_scout_targets: set[str] = set()
        self._dispatched_clear_targets: set[str] = set()
        self._pending_weaken_counts: dict[str, int] = {}

    def on_start(self, state: Any) -> None:
        self._dispatched_scout_targets.clear()
        self._dispatched_clear_targets.clear()
        self._pending_weaken_counts.clear()
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None or player.delivered:
            return []
        if state.phase == "RUSH" or player.squad_available <= 0:
            return []

        reserve = _squad_guard_reserve(context, self._route_policy)

        weaken_target = _weaken_target_on_route(context, self._pending_weaken_counts, self._route_policy)
        if weaken_target and player.squad_available >= 2:
            self._pending_weaken_counts[weaken_target] = self._pending_weaken_counts.get(weaken_target, 0) + 1
            self._logger.important(
                "squad_weaken_dispatch round=%s target=%s available=%s reserve=%s pending=%s"
                " | 小分队削弱：派出小分队降低敌方设卡防守值（消耗 2 人手，目标防守值 -2）",
                state.round_no,
                weaken_target,
                player.squad_available,
                reserve,
                self._pending_weaken_counts[weaken_target],
            )
            return [squad_weaken(weaken_target)]

        clear_target = _clear_target_on_route(context, self._dispatched_clear_targets, self._route_policy)
        if clear_target and player.squad_available - SQUAD_WEAKEN_COST >= reserve:
            self._dispatched_clear_targets.add(clear_target)
            self._logger.important(
                "squad_clear_dispatch round=%s target=%s available=%s reserve=%s"
                " | 小分队清障：派出小分队远程清除道路障碍（消耗 2 人手，不算完成 T04）",
                state.round_no,
                clear_target,
                player.squad_available,
                reserve,
            )
            return [squad_clear(clear_target)]

        if player.squad_available - 1 < reserve:
            if reserve:
                self._logger.trace(
                    "squad_reserve round=%s available=%s reserve=%s",
                    state.round_no,
                    player.squad_available,
                    reserve,
                )
            return []

        for target in SCOUT_TARGETS:
            if target in self._dispatched_scout_targets:
                continue
            if target not in state.game_map.nodes:
                continue
            if target in state.game_map.terminal_node_ids:
                continue
            if _has_own_scout_marker(context, target):
                self._dispatched_scout_targets.add(target)
                continue
            self._dispatched_scout_targets.add(target)
            self._logger.important(
                "squad_scout_dispatch round=%s target=%s available=%s"
                " | 小分队探路：派出小分队为目标节点添加己方探路标记（消耗 1 人手，后续该节点处理帧数 -3）",
                state.round_no,
                target,
                player.squad_available,
            )
            return [squad_scout(target)]
        return []


def _clear_target_on_route(
    context: StrategyContext,
    dispatched_clear_targets: set[str],
    route_policy: Optional[RoutePolicy],
) -> str:
    state = context.state
    player = state.me
    if player is None or not player.current_node_id:
        return ""

    target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = _route_path(state, player.current_node_id, target, route_policy)
    for node_id in path[1:]:
        if node_id in dispatched_clear_targets:
            continue
        node = state.nodes.get(node_id)
        if node is not None and node.has_obstacle:
            return node_id
    return ""


def _weaken_target_on_route(
    context: StrategyContext,
    pending_weaken_counts: dict[str, int],
    route_policy: Optional[RoutePolicy],
) -> str:
    state = context.state
    player = state.me
    if player is None or not player.current_node_id:
        return ""

    if player.state in ROUTE_EDGE_STATES and player.next_node_id:
        guard = enemy_guard_at(state.nodes.get(player.next_node_id), player)
        if guard is not None and _should_dispatch_weaken(
            context,
            player.next_node_id,
            guard.defense,
            pending_weaken_counts,
            force_until_clear=True,
        ):
            return player.next_node_id

    if player.state in ROUTE_EDGE_STATES and player.current_node_id:
        for node_id in state.game_map.neighbors(player.current_node_id):
            guard = enemy_guard_at(state.nodes.get(node_id), player)
            if guard is None:
                continue
            if _should_dispatch_weaken(
                context,
                node_id,
                guard.defense,
                pending_weaken_counts,
                force_until_clear=True,
            ):
                return node_id

    target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = _route_path(state, player.current_node_id, target, route_policy)
    for node_id in path[1:]:
        guard = enemy_guard_at(state.nodes.get(node_id), player)
        if guard is None:
            pending_weaken_counts.pop(node_id, None)
            continue
        if not _should_dispatch_weaken(context, node_id, guard.defense, pending_weaken_counts):
            continue
        return node_id
    return ""


def _should_dispatch_weaken(
    context: StrategyContext,
    target_node_id: str,
    defense: int,
    pending_weaken_counts: dict[str, int],
    *,
    force_until_clear: bool = False,
) -> bool:
    state = context.state
    player = state.me
    if player is None or defense <= 0:
        pending_weaken_counts.pop(target_node_id, None)
        return False

    pending = pending_weaken_counts.get(target_node_id, 0)
    if force_until_clear:
        return defense - pending * SQUAD_WEAKEN_VALUE > 0

    if _direct_break_can_clear(player, defense):
        return False
    return defense - pending * SQUAD_WEAKEN_VALUE > _max_direct_break_attack(player)


def _has_own_scout_marker(context: StrategyContext, target_node_id: str) -> bool:
    state = context.state
    player = state.me
    node = state.nodes.get(target_node_id)
    if player is None or node is None:
        return False
    markers = node.raw.get("scouted") or node.raw.get("scouts") or []
    for marker in markers:
        if marker.get("playerId") == state.player_id or marker.get("teamId") == player.team_id:
            return True
    return False


def _route_path(
    state: Any,
    current: str,
    target: str,
    route_policy: Optional[RoutePolicy],
) -> list[str]:
    if route_policy is not None:
        return route_policy.path(state, current, target)
    return state.game_map.fastest_path(current, target)


def _squad_guard_reserve(
    context: StrategyContext,
    route_policy: Optional[RoutePolicy],
) -> int:
    state = context.state
    player = state.me
    if player is None or not player.current_node_id or state.phase == "RUSH":
        return 0

    target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = _route_path(state, player.current_node_id, target, route_policy)
    reserve = 0
    for node_id in path[1:]:
        cap = _guard_cap_for_node(state, node_id)
        if cap <= 0:
            continue
        reserve = max(reserve, _squad_people_to_remove_guard(cap))
    if route_policy_is_speed_priority(route_policy):
        return min(4, reserve)
    return min(8, reserve)


def _guard_cap_for_node(state: Any, node_id: str) -> int:
    if node_id in CRITICAL_GUARD_CAPS:
        return CRITICAL_GUARD_CAPS[node_id]
    map_node = state.game_map.nodes.get(node_id)
    node_type = str(
        (map_node.raw if map_node else {}).get("nodeType")
        or (map_node.raw if map_node else {}).get("type")
        or ""
    ).upper()
    if node_type == "KEY_PASS":
        return 7
    if node_type == "GATE":
        return 4
    return 0


def _squad_people_to_remove_guard(defense: int) -> int:
    if defense <= 0:
        return 0
    return int(math.ceil(defense / SQUAD_WEAKEN_VALUE) * SQUAD_WEAKEN_COST)


def _direct_break_can_clear(player: Any, defense: int) -> bool:
    return _max_direct_break_attack(player) >= defense


def _max_direct_break_attack(player: Any) -> int:
    bad_fruit = min(2, int(getattr(player, "bad_fruit", 0) or 0))
    good_fruit = min(2, max(0, int(getattr(player, "good_fruit", 0) or 0) - 1))
    return bad_fruit * 3 + good_fruit * 2
