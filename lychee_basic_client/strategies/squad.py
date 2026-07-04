import math
from typing import Any, Optional

from lychee_basic_client.protocol.actions import squad_clear, squad_reinforce, squad_scout, squad_weaken
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.rules.guards import guard_max_defense, has_own_active_guard
from lychee_basic_client.rules.states import ROUTE_EDGE_STATES
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.routing import RoutePolicy
from lychee_basic_client.strategies.speed_priority import (
    WUGUAN_NODE_ID,
    WUGUAN_RACE_ROUTE,
    route_policy_is_speed_priority,
    route_policy_uses_fastest_wuguan,
)


SCOUT_TARGETS = ("S04", "S05", "S11", "S13", "S14")
SPEED_PRIORITY_SCOUT_TARGETS = ("S04", "S05")
SPEED_PRIORITY_SQUAD_RESERVE = 6
CRITICAL_GUARD_CAPS = {
    "S10": 7,
    "S11": 7,
    "S14": 4,
}
SQUAD_WEAKEN_COST = 2
SQUAD_WEAKEN_VALUE = 2
SQUAD_REINFORCE_COST = 2
SQUAD_REINFORCE_VALUE = 2
OWN_GUARD_PRIORITY = {
    "S10": 120,
    "S09": 110,
    "S11": 92,
    "S14": 88,
    "S13": 85,
}
MOVE_BLOCKED_BY_GUARD = "MOVE_BLOCKED_BY_GUARD"


class SquadStrategy:
    """小分队策略：产出可与主车队并行的探路、清障、增援和削弱决策。"""

    def __init__(self, route_policy: Optional[RoutePolicy] = None) -> None:
        self._route_policy = route_policy
        self._logger = get_logger("strategies.squad")
        self._dispatched_scout_targets: set[str] = set()
        self._dispatched_clear_targets: set[str] = set()
        self._pending_reinforce_counts: dict[str, int] = {}
        self._pending_weaken_counts: dict[str, int] = {}
        self._last_reinforce_target = ""

    def on_start(self, state: Any) -> None:
        self._dispatched_scout_targets.clear()
        self._dispatched_clear_targets.clear()
        self._pending_reinforce_counts.clear()
        self._pending_weaken_counts.clear()
        self._last_reinforce_target = ""
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        self._observe_reinforce_results(context)
        player = state.me
        if player is None or player.delivered:
            return []
        if state.phase == "RUSH" or player.squad_available <= 0:
            _log_weathered_guard_reinforce_skip(
                self._logger,
                context,
                self._pending_reinforce_counts,
                reason="宫宴冲刺阶段禁止新派小分队" if state.phase == "RUSH" else "小分队可用人数为 0",
            )
            return []

        # reserve 是保留给后续关键设卡的最低人手，避免前期探路/清障把破关资源耗空。
        reserve = _squad_guard_reserve(context, self._route_policy)

        # 已经被敌方设卡挡住时，削弱设卡优先级最高；该动作不占 main 类别。
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

        # 己方设卡已经生效后，小分队优先把关键关卡补到防守上限。
        reinforce_target = _reinforce_target_for_own_guard(
            context,
            self._pending_reinforce_counts,
        )
        if reinforce_target and player.squad_available >= SQUAD_REINFORCE_COST:
            self._pending_reinforce_counts[reinforce_target] = (
                self._pending_reinforce_counts.get(reinforce_target, 0) + 1
            )
            self._last_reinforce_target = reinforce_target
            node = state.nodes.get(reinforce_target)
            guard = (node.guard if node else None) or {}
            self._logger.important(
                "squad_reinforce_dispatch round=%s target=%s available=%s reserve=%s defense=%s max=%s pending=%s"
                " | 小分队增援：派出小分队加强己方有效设卡（消耗 2 人手，目标防守值 +2，不超过上限）",
                state.round_no,
                reinforce_target,
                player.squad_available,
                reserve,
                guard.get("defense"),
                _guard_max_defense(state, reinforce_target, guard),
                self._pending_reinforce_counts[reinforce_target],
            )
            return [squad_reinforce(reinforce_target)]
        _log_weathered_guard_reinforce_skip(
            self._logger,
            context,
            self._pending_reinforce_counts,
            reason=(
                f"小分队可用人数 {player.squad_available}，不足 {SQUAD_REINFORCE_COST}"
                if reinforce_target
                else ""
            ),
        )

        # 普通道路障碍可提前派小分队清理，但不能动用预留给关键关卡的人手。
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

        for target in _scout_targets_for_context(context, self._route_policy):
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

    def _observe_reinforce_results(self, context: StrategyContext) -> None:
        state = context.state
        for event in state.events:
            event_type = event.get("type")
            payload = event.get("payload") or {}
            if payload.get("playerId") not in (None, state.player_id):
                continue
            if event_type in {"ACTION_REJECTED", "INVALID_ACTION"} and payload.get("action") == "SQUAD_REINFORCE":
                target = str(payload.get("targetNodeId") or self._last_reinforce_target)
                if target:
                    self._pending_reinforce_counts.pop(target, None)
                continue
            if event_type == "SQUAD_FAILED" and payload.get("action") != "SQUAD_REINFORCE":
                continue
            if event_type not in {"SQUAD_REINFORCE", "SQUAD_FAILED"}:
                continue
            target = str(payload.get("targetNodeId") or payload.get("nodeId") or "")
            if target:
                self._pending_reinforce_counts.pop(target, None)

        for result in state.action_results:
            if result.get("playerId") != state.player_id:
                continue
            if result.get("action") != "SQUAD_REINFORCE":
                continue
            if result.get("accepted", True):
                continue
            target = str(result.get("targetNodeId") or self._last_reinforce_target)
            if target:
                self._pending_reinforce_counts.pop(target, None)


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
        forward_adjacent_target = _forward_adjacent_weaken_target(
            context,
            pending_weaken_counts,
            route_policy,
        )
        if forward_adjacent_target:
            return forward_adjacent_target

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


def _forward_adjacent_weaken_target(
    context: StrategyContext,
    pending_weaken_counts: dict[str, int],
    route_policy: Optional[RoutePolicy],
) -> str:
    state = context.state
    player = state.me
    if player is None or not player.current_node_id:
        return ""

    target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = _route_path(state, player.current_node_id, target, route_policy)
    if len(path) < 2:
        return ""

    neighbors = set(state.game_map.neighbors(player.current_node_id))
    for node_id in path[1:]:
        if node_id not in neighbors:
            continue
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


def _reinforce_target_for_own_guard(
    context: StrategyContext,
    pending_reinforce_counts: dict[str, int],
) -> str:
    state = context.state
    player = state.me
    if player is None:
        return ""

    for node_id, node in state.nodes.items():
        if not has_own_active_guard(node, player):
            pending_reinforce_counts.pop(node_id, None)

    # 存在多个己方设卡时，只增援优先级最高的关卡（如 S10 优先于 S09）。
    # S09 即便风化，只要 S10 设卡仍有效，就不增援 S09，节省小分队人手。
    target_node_id = _top_priority_own_guard_node(context)
    if not target_node_id:
        return ""

    node = state.nodes.get(target_node_id)
    guard = (node.guard if node else None) or {}
    defense = int(guard.get("defense") or 0)
    max_defense = _guard_max_defense(state, target_node_id, guard)
    pending = pending_reinforce_counts.get(target_node_id, 0)
    if not _should_reinforce_guard(defense, max_defense, pending):
        return ""
    if not _opponent_pressure_reason_for_guard(state, player, target_node_id):
        return ""
    return target_node_id


def _top_priority_own_guard_node(context: StrategyContext) -> str:
    """选择优先级最高的己方设卡节点；优先级相同时选距离最近的。"""
    state = context.state
    player = state.me
    if player is None:
        return ""

    candidates: list[tuple[int, int, str]] = []
    for node_id, node in state.nodes.items():
        if not has_own_active_guard(node, player):
            continue
        candidates.append(
            (
                -_own_guard_priority(state, node_id),
                _guard_distance_from_player(state, player, node_id),
                node_id,
            )
        )
    if not candidates:
        return ""
    return min(candidates)[2]


def _guard_distance_from_player(state: Any, player: Any, node_id: str) -> int:
    if not getattr(player, "current_node_id", ""):
        return 1_000_000_000
    distance = state.game_map.route_distance(player.current_node_id, node_id)
    if distance is None:
        return 1_000_000_000
    return distance


def _should_reinforce_guard(defense: int, max_defense: int, pending: int) -> bool:
    effective_defense = defense + pending * SQUAD_REINFORCE_VALUE
    missing = max_defense - effective_defense
    return missing >= SQUAD_REINFORCE_VALUE


def _guard_max_defense(state: Any, node_id: str, guard: dict[str, Any]) -> int:
    explicit = guard.get("maxDefense")
    if explicit not in (None, ""):
        return int(explicit)
    return guard_max_defense(state, node_id)


def _own_guard_priority(state: Any, node_id: str) -> int:
    if node_id in OWN_GUARD_PRIORITY:
        return OWN_GUARD_PRIORITY[node_id]
    map_node = state.game_map.nodes.get(node_id)
    node_type = str(
        (map_node.raw if map_node else {}).get("nodeType")
        or (map_node.raw if map_node else {}).get("type")
        or ""
    ).upper()
    if node_type == "KEY_PASS":
        return 100
    if node_type == "GATE":
        return 80
    return 50


def _opponent_pressure_reason_for_guard(state: Any, player: Any, node_id: str) -> str:
    for other in state.players.values():
        if other.player_id == player.player_id or other.team_id == player.team_id:
            continue
        if not other.current_node_id:
            continue
        if _recent_move_blocked_by_guard(state, other.player_id, node_id):
            return f"对手 {other.player_id} 上帧 MOVE 被己方设卡阻挡"
        if other.next_node_id == node_id:
            return f"对手 {other.player_id} 当前朝向该节点"
        target = state.game_map.terminal_node_ids[0] if other.verified else state.game_map.gate_node_id
        path = state.game_map.fastest_path(other.current_node_id, target)
        if node_id in path[1:]:
            return f"对手 {other.player_id} 后续最快路径仍需经过该节点"
    return ""


def _recent_move_blocked_by_guard(state: Any, opponent_player_id: int, node_id: str) -> bool:
    for result in state.action_results:
        if result.get("playerId") != opponent_player_id:
            continue
        if result.get("action") != "MOVE":
            continue
        if result.get("accepted", True):
            continue
        error = str(result.get("errorCode") or result.get("result") or "")
        if error != MOVE_BLOCKED_BY_GUARD:
            continue
        target = str(result.get("targetNodeId") or "")
        if not target or target == node_id:
            return True

    for event in state.events:
        if event.get("type") not in {"ACTION_REJECTED", "INVALID_ACTION"}:
            continue
        payload = event.get("payload") or {}
        if payload.get("playerId") != opponent_player_id:
            continue
        if payload.get("action") not in (None, "MOVE"):
            continue
        if payload.get("errorCode") != MOVE_BLOCKED_BY_GUARD:
            continue
        target = str(payload.get("targetNodeId") or "")
        if not target or target == node_id:
            return True
    return False


def _log_weathered_guard_reinforce_skip(
    logger: Any,
    context: StrategyContext,
    pending_reinforce_counts: dict[str, int],
    *,
    reason: str = "",
) -> None:
    state = context.state
    player = state.me
    if player is None:
        return
    weathered_nodes = _weathered_guard_nodes(state)
    for node_id in sorted(weathered_nodes):
        node = state.nodes.get(node_id)
        if not has_own_active_guard(node, player):
            continue
        guard = node.guard or {}
        defense = int(guard.get("defense") or 0)
        max_defense = _guard_max_defense(state, node_id, guard)
        pending = pending_reinforce_counts.get(node_id, 0)
        pressure_reason = _opponent_pressure_reason_for_guard(state, player, node_id)
        skip_reason = reason
        effective_defense = defense + pending * SQUAD_REINFORCE_VALUE
        missing = max_defense - effective_defense
        if not skip_reason and missing <= 0:
            skip_reason = "当前防守值加在途增援已达到防守上限"
        if not skip_reason and 0 < missing < SQUAD_REINFORCE_VALUE:
            skip_reason = (
                f"当前只缺 {missing} 点防守值，低于一次小分队增援 +{SQUAD_REINFORCE_VALUE} 的收益，暂不派出"
            )
        if not skip_reason and not pressure_reason:
            skip_reason = "未识别到对手仍需经过该节点或正被该节点设卡阻挡"
        if not skip_reason:
            continue
        logger.important(
            "squad_reinforce_skip round=%s target=%s defense=%s max=%s pending=%s available=%s reason=%s pressure=%s"
            " | 小分队增援跳过：己方设卡刚发生风化，但本帧未派出增援。目标=%s，防守=%s/%s，在途增援=%s，可用小分队=%s，原因=%s，对手压力=%s",
            state.round_no,
            node_id,
            defense,
            max_defense,
            pending,
            player.squad_available,
            skip_reason,
            pressure_reason or "无",
            node_id,
            defense,
            max_defense,
            pending,
            player.squad_available,
            skip_reason,
            pressure_reason or "无",
        )


def _weathered_guard_nodes(state: Any) -> set[str]:
    nodes: set[str] = set()
    for event in state.events:
        if event.get("type") != "GUARD_WEATHERING":
            continue
        payload = event.get("payload") or {}
        node_id = str(payload.get("nodeId") or payload.get("targetNodeId") or "")
        if node_id:
            nodes.add(node_id)
    return nodes


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


def _scout_targets_for_context(
    context: StrategyContext,
    route_policy: Optional[RoutePolicy],
) -> tuple[str, ...]:
    if not route_policy_is_speed_priority(route_policy):
        return SCOUT_TARGETS
    if route_policy_uses_fastest_wuguan(route_policy):
        return ()
    state = context.state
    player = state.me
    current = player.current_node_id if player else None
    if not current or current not in WUGUAN_RACE_ROUTE:
        return ()
    current_index = WUGUAN_RACE_ROUTE.index(current)
    wuguan_index = WUGUAN_RACE_ROUTE.index(WUGUAN_NODE_ID)
    if current_index >= wuguan_index:
        return ()
    return tuple(
        target
        for target in SPEED_PRIORITY_SCOUT_TARGETS
        if target in WUGUAN_RACE_ROUTE
        and current_index < WUGUAN_RACE_ROUTE.index(target) < wuguan_index
    )


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
        if reserve <= 0:
            return SPEED_PRIORITY_SQUAD_RESERVE
        return min(SPEED_PRIORITY_SQUAD_RESERVE, reserve)
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
