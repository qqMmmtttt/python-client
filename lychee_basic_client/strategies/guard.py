from typing import Any, Optional

from lychee_basic_client.models.state import GameState, PlayerState
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.planning.estimates import estimate_delivery_rounds, estimate_path_rounds
from lychee_basic_client.planning.tasks import TASK_SCORE_GOAL
from lychee_basic_client.protocol.actions import set_guard
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.rules.guards import (
    MAX_ACTIVE_OWN_GUARDS,
    active_own_guard_count,
    guard_base_good_fruit_cost,
    has_active_guard,
    max_effective_extra_good_fruit,
)
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.speed_priority import (
    FASTEST_WUGUAN_PROFILE,
    WUGUAN_GUARD_MIN_OPPONENT_ETA,
    WUGUAN_NODE_ID,
    opponent_eta_to_wuguan,
    route_policy_is_speed_priority,
)
from lychee_basic_client.strategies.wuguan_trap import WuguanTrapGuardPlan


KEY_GUARD_NODES = {
    "S10": 120,
    "S11": 92,
    "S13": 85,
}
NODE_TYPE_GUARD_SCORE = {
    "KEY_PASS": 112,
    "GATE": 88,
    "PASS": 84,
    "PALACE_STATION": 70,
    "STATION": 60,
}
MIN_GUARD_SCORE = 80
MIN_OPPONENT_ETA = 4
MAX_OPPONENT_ETA = 180
STRATEGY_PROFILE_WUGUAN_TRAP = "wuguan-trap"
STRATEGY_PROFILE_FASTEST_WUGUAN = FASTEST_WUGUAN_PROFILE
STRATEGY_PROFILE_SPEED_GUARD = "speed-guard"
STRATEGY_PROFILE_BALANCED = "balanced"


class GuardStrategy:
    """主动设卡策略：在己方时间安全且能明显拖慢对手时消耗好果设卡。"""

    def __init__(
        self,
        route_policy: Any = None,
        *,
        strategy_profile: str = STRATEGY_PROFILE_WUGUAN_TRAP,
    ) -> None:
        self._route_policy = route_policy
        self._strategy_profile = strategy_profile
        self._wuguan_trap = WuguanTrapGuardPlan(
            enable_luoyang_stage=strategy_profile == STRATEGY_PROFILE_WUGUAN_TRAP
        )
        self._attempted_nodes: set[str] = set()
        self._logger = get_logger("strategies.guard")
        self._flow = get_logger("guard_flow")

    def on_start(self, state: Any) -> None:
        self._attempted_nodes.clear()
        self._wuguan_trap.on_start()
        return None

    def _log_wuguan(self, state: GameState, current: str, reason: str, **detail: Any) -> None:
        parts = " ".join(f"{k}={v}" for k, v in detail.items())
        self._flow.important(
            "wuguan_guard round=%s node=%s reason=%s %s | 武关设卡诊断：%s",
            state.round_no, current, reason, parts, reason,
        )

    def _log_wuguan_opponents(self, state: GameState, current: str) -> None:
        player = state.me
        if player is None:
            return
        for other in state.players.values():
            if other.player_id == player.player_id or other.team_id == player.team_id:
                continue
            other_node = other.current_node_id
            if not other_node:
                continue
            target = state.game_map.terminal_node_ids[0] if other.verified else state.game_map.gate_node_id
            path = state.game_map.fastest_path(other_node, target)
            through_wuguan = WUGUAN_NODE_ID in path
            eta = None
            if through_wuguan:
                path_to_wuguan = path[: path.index(WUGUAN_NODE_ID) + 1]
                eta = estimate_path_rounds(state, path_to_wuguan, include_process=True)
            self._flow.important(
                "wuguan_guard_opponent round=%s node=%s opp_id=%s opp_node=%s verified=%s target=%s path=%s through_wuguan=%s eta=%s"
                " | 武关设卡诊断：对手路径与ETA分析",
                state.round_no, current, other.player_id, other_node, other.verified, target,
                "->".join(path) if path else "N/A", through_wuguan, eta,
            )

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        current = player.current_node_id if player else None
        is_wuguan = current == WUGUAN_NODE_ID
        is_luoyang_wuguan_trap = self._strategy_profile == STRATEGY_PROFILE_WUGUAN_TRAP
        is_fastest_wuguan_trap = self._strategy_profile == STRATEGY_PROFILE_FASTEST_WUGUAN
        is_trap_node = (
            (is_luoyang_wuguan_trap and current in {"S09", WUGUAN_NODE_ID})
            or (is_fastest_wuguan_trap and current == WUGUAN_NODE_ID)
        )
        allow_rush_wuguan_trap = (
            state.phase == "RUSH"
            and is_trap_node
            and current == WUGUAN_NODE_ID
        )

        if player is None or player.delivered:
            if is_wuguan:
                self._log_wuguan(state, current, "player_none_or_delivered",
                                 delivered=getattr(player, "delivered", None))
            return []
        node_waiting = player.state == "WAITING" and not player.next_node_id
        if (state.phase == "RUSH" and not allow_rush_wuguan_trap) or player.current_process or (
            player.state != "IDLE" and not node_waiting
        ):
            if is_wuguan:
                self._log_wuguan(state, current, "not_idle_or_rush",
                                 phase=state.phase, player_state=player.state,
                                 current_process=player.current_process)
            return []

        current = player.current_node_id
        trap_can_retry_wuguan = is_trap_node and current == WUGUAN_NODE_ID
        if not current or (current in self._attempted_nodes and not trap_can_retry_wuguan):
            if is_wuguan:
                self._log_wuguan(state, current, "already_attempted",
                                 in_attempted=current in self._attempted_nodes)
            return []
        active_count = active_own_guard_count(state, player)
        if active_count >= MAX_ACTIVE_OWN_GUARDS and not is_trap_node:
            if is_wuguan:
                self._log_wuguan(state, current, "max_guards_reached",
                                 active_count=active_count, max_guards=MAX_ACTIVE_OWN_GUARDS)
            return []

        node = state.nodes.get(current)
        if node is None:
            if is_wuguan:
                self._log_wuguan(state, current, "node_not_in_state")
            return []

        if is_trap_node:
            trap_decision = self._wuguan_trap_decision(state, player, current, active_count)
            if trap_decision is not None:
                action = trap_decision.action
                if action.get("action") == "SET_GUARD" and not trap_can_retry_wuguan:
                    self._attempted_nodes.add(current)
                return [action]
            return []

        has_own = has_active_guard(node)
        has_enemy = enemy_guard_at(node, player) is not None
        if has_own or has_enemy:
            if is_wuguan:
                self._log_wuguan(state, current, "already_guarded",
                                 has_own=has_own, has_enemy=has_enemy)
            return []

        speed_guard = self._speed_priority_wuguan_guard(state, player, current)
        if speed_guard is not None:
            self._attempted_nodes.add(current)
            return [speed_guard]

        # 非速度优先场景：先保证任务得分基础，再用剩余时间窗口主动设卡。
        if player.task_score < TASK_SCORE_GOAL:
            if is_wuguan:
                self._log_wuguan(state, current, "task_score_below_goal",
                                 task_score=player.task_score, goal=TASK_SCORE_GOAL)
            return []
        if state.round_no >= 420 and current != "S13":
            if is_wuguan:
                self._log_wuguan(state, current, "round_too_late_normal",
                                 round_no=state.round_no, limit=420)
            return []

        candidate_score = _guard_candidate_score(state, current)
        if candidate_score < MIN_GUARD_SCORE:
            if is_wuguan:
                self._log_wuguan(state, current, "candidate_score_too_low",
                                 candidate_score=candidate_score, min=MIN_GUARD_SCORE)
            return []
        if _creates_large_bounty_risk(state, player):
            if is_wuguan:
                self._log_wuguan(state, current, "large_bounty_risk",
                                 total_score=player.total_score)
            return []
        if not _delivery_has_guard_slack(state, player, current):
            if is_wuguan:
                delivery_total = state.round_no + estimate_delivery_rounds(
                    state, current, player.verified) + 100
                self._log_wuguan(state, current, "no_delivery_slack_normal",
                                 round_no=state.round_no, delivery_total=delivery_total, limit=600)
            return []
        if not _opponent_will_need_node(state, player, current):
            if is_wuguan:
                self._log_wuguan(state, current, "opponent_not_need_node_normal")
                self._log_wuguan_opponents(state, current)
            return []

        extra_good_fruit = _extra_good_fruit_for_guard(state, player, current, candidate_score)
        base_cost = guard_base_good_fruit_cost(state, current)
        threshold = base_cost + extra_good_fruit + 18
        if player.good_fruit <= threshold:
            if is_wuguan:
                self._log_wuguan(state, current, "not_enough_good_fruit_normal",
                                 good_fruit=player.good_fruit, threshold=threshold,
                                 base_cost=base_cost, extra=extra_good_fruit)
            return []

        self._attempted_nodes.add(current)
        self._logger.important(
            "set_guard round=%s node=%s extra_good=%s candidate_score=%s | 设卡：在关键节点建立己方设卡阻挡敌方通行（4 帧处理，防守值 = 2 + 投入×2）",
            state.round_no,
            current,
            extra_good_fruit,
            candidate_score,
        )
        return [set_guard(current, extra_good_fruit=extra_good_fruit)]

    def _speed_priority_wuguan_guard(
        self,
        state: GameState,
        player: PlayerState,
        current: str,
    ) -> Optional[dict[str, Any]]:
        if self._strategy_profile != STRATEGY_PROFILE_SPEED_GUARD:
            if current == WUGUAN_NODE_ID:
                self._log_wuguan(
                    state,
                    current,
                    "profile_skip_direct_speed_guard",
                    strategy_profile=self._strategy_profile,
                )
            return None
        if not route_policy_is_speed_priority(self._route_policy):
            if current == WUGUAN_NODE_ID:
                self._log_wuguan(state, current, "not_speed_priority_profile")
            return None
        if current != WUGUAN_NODE_ID:
            return None
        if state.round_no >= 360:
            self._log_wuguan(state, current, "round_too_late_speed",
                             round_no=state.round_no, limit=360)
            return None
        has_slack = _delivery_has_guard_slack(state, player, current)
        if not has_slack:
            delivery_total = state.round_no + estimate_delivery_rounds(
                state, current, player.verified) + 100
            self._log_wuguan(state, current, "no_delivery_slack_speed",
                             round_no=state.round_no, delivery_total=delivery_total, limit=600,
                             verified=player.verified)
            return None
        opp_will_need = _opponent_will_need_node(state, player, current)
        if not opp_will_need:
            self._log_wuguan(state, current, "opponent_not_need_node_speed")
            self._log_wuguan_opponents(state, current)
            return None
        opponent_eta = opponent_eta_to_wuguan(state, player)
        if opponent_eta is None or opponent_eta < WUGUAN_GUARD_MIN_OPPONENT_ETA:
            self._log_wuguan(state, current, "opponent_eta_none_or_too_close",
                             opponent_eta=opponent_eta,
                             min_required=WUGUAN_GUARD_MIN_OPPONENT_ETA)
            self._log_wuguan_opponents(state, current)
            return None
        extra_good_fruit = max_effective_extra_good_fruit(state, current)
        base_cost = guard_base_good_fruit_cost(state, current)
        threshold = base_cost + extra_good_fruit + 12
        if player.good_fruit <= threshold:
            self._log_wuguan(state, current, "not_enough_good_fruit_speed",
                             good_fruit=player.good_fruit, threshold=threshold,
                             base_cost=base_cost, extra=extra_good_fruit,
                             opponent_eta=opponent_eta)
            return None
        self._flow.important(
            "wuguan_guard_pass round=%s node=%s opponent_eta=%s extra_good=%s good=%s base_cost=%s"
            " | 武关设卡诊断：所有条件通过，提交 SET_GUARD",
            state.round_no, current, opponent_eta, extra_good_fruit, player.good_fruit, base_cost,
        )
        self._logger.important(
            "set_guard_speed_priority round=%s node=%s opponent_eta=%s extra_good=%s good=%s"
            " | 速度优先：我方已先到武关，且对手到达武关仍有足够距离，立即设卡拖慢对方入关节奏",
            state.round_no,
            current,
            opponent_eta,
            extra_good_fruit,
            player.good_fruit,
        )
        return set_guard(current, extra_good_fruit=extra_good_fruit)

    def _wuguan_trap_decision(
        self,
        state: GameState,
        player: PlayerState,
        current: str,
        active_count: int,
    ) -> Optional[Any]:
        return self._wuguan_trap.decide(
            state,
            player,
            active_guard_count=active_count,
        )


def _delivery_has_guard_slack(state: GameState, player: PlayerState, current: str) -> bool:
    if current == "S13":
        margin = 8
    else:
        margin = 100 if current != state.game_map.gate_node_id else 70
    return state.round_no + estimate_delivery_rounds(
        state,
        current,
        player.verified,
    ) + margin < 600


def _guard_candidate_score(state: GameState, current: str) -> int:
    if current in state.game_map.terminal_node_ids or current == state.game_map.start_node_id:
        return 0
    map_node = state.game_map.nodes.get(current)
    node_type = str(
        (map_node.raw if map_node else {}).get("nodeType")
        or (map_node.raw if map_node else {}).get("type")
        or ""
    ).upper()
    return max(
        KEY_GUARD_NODES.get(current, 0),
        NODE_TYPE_GUARD_SCORE.get(node_type, 0),
    )


def _opponent_will_need_node(state: GameState, player: PlayerState, current: str) -> bool:
    for other in state.players.values():
        if other.player_id == player.player_id or other.team_id == player.team_id:
            continue
        other_node = other.current_node_id
        if not other_node:
            continue
        target = state.game_map.terminal_node_ids[0] if other.verified else state.game_map.gate_node_id
        path = state.game_map.fastest_path(other_node, target)
        if current not in path[1:]:
            continue
        eta = estimate_path_rounds(state, path[: path.index(current) + 1], include_process=True)
        if MIN_OPPONENT_ETA <= eta <= MAX_OPPONENT_ETA:
            return True
    return False


def _extra_good_fruit_for_guard(
    state: GameState,
    player: PlayerState,
    current: str,
    candidate_score: int,
) -> int:
    return max_effective_extra_good_fruit(state, current)


def _creates_large_bounty_risk(state: GameState, player: PlayerState) -> bool:
    if player.total_score <= 0:
        return False
    for other in state.players.values():
        if other.player_id == player.player_id or other.team_id == player.team_id:
            continue
        if other.total_score > 0 and player.total_score - other.total_score >= 60:
            return True
    return False
