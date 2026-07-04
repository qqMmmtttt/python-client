from dataclasses import dataclass
import math
from typing import Optional

from lychee_basic_client.models.state import GameState, PlayerState
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.planning.estimates import estimate_delivery_rounds, estimate_path_rounds
from lychee_basic_client.protocol.actions import set_guard, wait
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.rules.guards import (
    GUARD_PROCESS_ROUNDS,
    MAX_ACTIVE_OWN_GUARDS,
    active_own_guard_count,
    can_pay_guard,
    guard_base_good_fruit_cost,
    guard_defense_after_extra,
    has_own_active_guard,
    max_effective_extra_good_fruit,
)


LUOYANG_NODE_ID = "S09"
WUGUAN_NODE_ID = "S10"
LUOYANG_GUARD_RESERVE_GOOD_FRUIT = 8
WUGUAN_GUARD_RESERVE_GOOD_FRUIT = 6
LUOYANG_MAX_USEFUL_OPPONENT_ETA = 150
WUGUAN_SET_DELIVERY_MARGIN = 65
WUGUAN_FORCE_SET_ROUND = 500
WUGUAN_DELIVERY_SAFETY_MARGIN = 8
WUGUAN_DELIVERY_SAFETY_LIMIT_ENABLED = False


@dataclass(frozen=True)
class WuguanTrapDecision:
    action: dict[str, object]
    stage: str


@dataclass(frozen=True)
class WuguanApproachStatus:
    should_set_guard: bool
    reason: str
    wait_detail: str = ""


@dataclass(frozen=True)
class WuguanDeadline:
    selected_round: int
    hard_limit_round: int
    safety_enabled: bool
    latest_safe_round: int
    delivery_estimate_rounds: int
    guard_process_rounds: int
    safety_margin: int

    @property
    def triggered_by_safety(self) -> bool:
        return self.safety_enabled and self.selected_round < self.hard_limit_round


class WuguanTrapGuardPlan:
    """洛阳驿 + 武关双段设卡局部策略。

    目标流程：
    1. 我方先到 S09 洛阳驿，且对手还没到洛阳时，最大投入在 S09 设卡。
    2. 我方抵达 S10 武关后，不立刻设卡；等待对手进入武关前置触发区。
    3. 对手从 S09 直奔 S10，或经 S08 秦岭栈道接近 S10 时，最大投入在 S10 设卡。
    """

    def __init__(self, *, enable_luoyang_stage: bool = True) -> None:
        self._enable_luoyang_stage = enable_luoyang_stage
        self._logger = get_logger("strategies.wuguan_trap")
        self._flow = get_logger("guard_flow")
        self._luoyang_guard_submitted = False
        self._luoyang_guard_seen_active = False
        self._wuguan_guard_submitted = False

    def on_start(self) -> None:
        self._luoyang_guard_submitted = False
        self._luoyang_guard_seen_active = False
        self._wuguan_guard_submitted = False

    def decide(
        self,
        state: GameState,
        player: PlayerState,
        *,
        active_guard_count: int,
    ) -> Optional[WuguanTrapDecision]:
        self._observe_own_guards(state, player)
        if self._enable_luoyang_stage and player.current_node_id == LUOYANG_NODE_ID:
            return self._decide_at_luoyang(state, player, active_guard_count)
        if player.current_node_id == WUGUAN_NODE_ID:
            return self._decide_at_wuguan(state, player, active_guard_count)
        return None

    def _observe_own_guards(self, state: GameState, player: PlayerState) -> None:
        if self._enable_luoyang_stage and has_own_active_guard(state.nodes.get(LUOYANG_NODE_ID), player):
            self._luoyang_guard_seen_active = True
        if has_own_active_guard(state.nodes.get(WUGUAN_NODE_ID), player):
            self._wuguan_guard_submitted = True
        elif _own_wuguan_guard_removed_this_round(state, player):
            self._wuguan_guard_submitted = False

    def _decide_at_luoyang(
        self,
        state: GameState,
        player: PlayerState,
        active_guard_count: int,
    ) -> Optional[WuguanTrapDecision]:
        node = state.nodes.get(LUOYANG_NODE_ID)
        if node is None:
            self._log("洛阳设卡跳过", state, player, "服务器本轮未公开 S09 节点状态")
            return None
        if self._luoyang_guard_submitted or self._luoyang_guard_seen_active:
            return None
        if active_guard_count >= MAX_ACTIVE_OWN_GUARDS:
            self._log("洛阳设卡跳过", state, player, "己方有效设卡已达到 2 个上限")
            return None
        if has_own_active_guard(node, player) or enemy_guard_at(node, player) is not None:
            self._log("洛阳设卡跳过", state, player, "S09 已有有效设卡")
            return None

        opponent_eta = opponent_eta_to_node(state, player, LUOYANG_NODE_ID)
        if opponent_eta is None:
            self._log("洛阳设卡跳过", state, player, "没有发现会经过 S09 的对手")
            return None
        if opponent_eta <= GUARD_PROCESS_ROUNDS:
            self._log(
                "洛阳设卡跳过",
                state,
                player,
                f"对手到 S09 仅剩 {opponent_eta} 帧，设卡 4 帧读条来不及生效",
            )
            return None
        if opponent_eta > LUOYANG_MAX_USEFUL_OPPONENT_ETA:
            self._log(
                "洛阳设卡跳过",
                state,
                player,
                f"对手到 S09 预计 {opponent_eta} 帧，风化风险过高",
            )
            return None

        extra = max_effective_extra_good_fruit(state, LUOYANG_NODE_ID)
        future_wuguan_cost = guard_base_good_fruit_cost(state, WUGUAN_NODE_ID) + max_effective_extra_good_fruit(
            state, WUGUAN_NODE_ID
        )
        reserve = LUOYANG_GUARD_RESERVE_GOOD_FRUIT + future_wuguan_cost
        if not can_pay_guard(
            state,
            player,
            LUOYANG_NODE_ID,
            extra,
            reserve_good_fruit=reserve,
        ):
            self._log(
                "洛阳设卡跳过",
                state,
                player,
                f"好果不足，当前 {player.good_fruit}，需要保留武关设卡与交付余量 {reserve}",
            )
            return None
        if not _has_delivery_slack(state, player, LUOYANG_NODE_ID, WUGUAN_SET_DELIVERY_MARGIN):
            self._log("洛阳设卡跳过", state, player, "设卡后交付安全余量不足")
            return None

        self._luoyang_guard_submitted = True
        defense = guard_defense_after_extra(state, LUOYANG_NODE_ID, extra)
        self._log(
            "洛阳设卡提交",
            state,
            player,
            f"对手 ETA={opponent_eta}，extraGoodFruit={extra}，预计防守值={defense}",
        )
        return WuguanTrapDecision(
            action=set_guard(LUOYANG_NODE_ID, extra_good_fruit=extra),
            stage="luoyang_guard",
        )

    def _decide_at_wuguan(
        self,
        state: GameState,
        player: PlayerState,
        active_guard_count: int,
    ) -> Optional[WuguanTrapDecision]:
        node = state.nodes.get(WUGUAN_NODE_ID)
        if node is None:
            self._log("武关设卡跳过", state, player, "服务器本轮未公开 S10 节点状态")
            return None
        deadline = _wuguan_deadline(state, player)
        self._log_deadline(state, player, deadline)
        force_set_round = deadline.selected_round
        if has_own_active_guard(node, player):
            return self._decide_with_active_wuguan_guard(state, player, force_set_round)
        if enemy_guard_at(node, player) is not None:
            self._log("武关设卡跳过", state, player, "S10 已有敌方有效设卡")
            return None
        if active_guard_count >= MAX_ACTIVE_OWN_GUARDS and not (
            self._enable_luoyang_stage
            and has_own_active_guard(state.nodes.get(LUOYANG_NODE_ID), player)
        ):
            self._log("武关设卡跳过", state, player, "己方有效设卡已达到 2 个上限")
            return None

        approach_status = opponent_wuguan_approach_status(state, player)
        opponent_eta = opponent_eta_to_node(state, player, WUGUAN_NODE_ID)
        if state.round_no >= force_set_round and self._wuguan_wait_stage_active():
            reason = (
                f"交付安全保护触发：计算截止轮 {force_set_round}，立即武关设卡后转入终点主线"
                if deadline.triggered_by_safety
                else f"已到 {WUGUAN_FORCE_SET_ROUND} 轮等待硬上限，立即武关设卡后转入终点主线"
            )
            return self._set_wuguan_guard(
                state,
                player,
                opponent_eta=opponent_eta,
                reason=reason,
                allow_close_opponent=True,
            )
        should_fallback_set = self._should_fallback_set_wuguan(state, player, opponent_eta)
        if approach_status.should_set_guard or should_fallback_set:
            return self._set_wuguan_guard(
                state,
                player,
                opponent_eta=opponent_eta,
                reason=approach_status.reason if approach_status.should_set_guard else "未形成洛阳阶段，直接补武关设卡",
            )

        if self._wuguan_wait_stage_active():
            if opponent_eta is None:
                self._log(
                    "武关等待结束",
                    state,
                    player,
                    "未发现仍需经过武关的对手，停止等待并转入终点主线",
                )
                return None
            wait_detail = approach_status.wait_detail or "等待对手进入武关前置路径"
            self._log(
                "武关等待",
                state,
                player,
                f"{self._wuguan_wait_stage_label()}；{wait_detail}，当前对手到 S10 ETA={opponent_eta}，"
                f"武关等待截止轮={force_set_round}",
            )
            return WuguanTrapDecision(action=wait(), stage="wuguan_hold")
        return None

    def _wuguan_wait_stage_active(self) -> bool:
        if not self._enable_luoyang_stage:
            return True
        return self._luoyang_guard_submitted or self._luoyang_guard_seen_active

    def _wuguan_wait_stage_label(self) -> str:
        if self._enable_luoyang_stage:
            return "洛阳阶段已启动"
        return "最快武关策略已到达 S10"

    def _decide_with_active_wuguan_guard(
        self,
        state: GameState,
        player: PlayerState,
        force_set_round: int,
    ) -> Optional[WuguanTrapDecision]:
        if state.round_no >= force_set_round:
            self._log(
                "武关等待结束",
                state,
                player,
                f"己方武关设卡仍有效，但已到武关等待截止轮 {force_set_round}，转入终点主线",
            )
            return None

        opponent_eta = opponent_eta_to_node(state, player, WUGUAN_NODE_ID)
        approach_status = opponent_wuguan_approach_status(state, player)
        recently_blocked = _opponent_recently_blocked_by_wuguan(state, player)
        if recently_blocked or approach_status.should_set_guard or approach_status.wait_detail:
            detail = (
                "对手上一帧被武关设卡阻挡"
                if recently_blocked
                else approach_status.reason or approach_status.wait_detail
            )
            self._log(
                "武关设卡后继续等待",
                state,
                player,
                f"{detail}；己方武关设卡仍有效，等待其被消耗后再按窗口补设；"
                f"opponentETA={opponent_eta}，武关等待截止轮={force_set_round}",
            )
            return WuguanTrapDecision(action=wait(), stage="wuguan_guard_hold")

        if opponent_eta is not None and opponent_eta > 0:
            self._log(
                "武关设卡后继续等待",
                state,
                player,
                f"对手仍需经过武关，ETA={opponent_eta}，武关等待截止轮={force_set_round}",
            )
            return WuguanTrapDecision(action=wait(), stage="wuguan_guard_hold")

        self._log(
            "武关等待结束",
            state,
            player,
            "未发现对手仍处于武关前置路径或被武关设卡阻挡，转入终点主线",
        )
        return None

    def _should_fallback_set_wuguan(
        self,
        state: GameState,
        player: PlayerState,
        opponent_eta: Optional[int],
    ) -> bool:
        if not self._enable_luoyang_stage:
            return False
        if self._luoyang_guard_submitted or self._luoyang_guard_seen_active:
            return False
        if opponent_eta is None:
            return False
        if opponent_eta <= GUARD_PROCESS_ROUNDS:
            return False
        return _has_delivery_slack(state, player, WUGUAN_NODE_ID, WUGUAN_SET_DELIVERY_MARGIN)

    def _set_wuguan_guard(
        self,
        state: GameState,
        player: PlayerState,
        *,
        opponent_eta: Optional[int],
        reason: str,
        allow_close_opponent: bool = False,
    ) -> Optional[WuguanTrapDecision]:
        extra = max_effective_extra_good_fruit(state, WUGUAN_NODE_ID)
        if not can_pay_guard(
            state,
            player,
            WUGUAN_NODE_ID,
            extra,
            reserve_good_fruit=WUGUAN_GUARD_RESERVE_GOOD_FRUIT,
        ):
            self._log(
                "武关设卡跳过",
                state,
                player,
                f"好果不足，当前 {player.good_fruit}，无法支付武关基础成本和最大额外投入",
            )
            return None
        if (
            not allow_close_opponent
            and opponent_eta is not None
            and opponent_eta <= GUARD_PROCESS_ROUNDS
        ):
            self._log(
                "武关设卡跳过",
                state,
                player,
                f"对手到 S10 仅剩 {opponent_eta} 帧，设卡无法在其到达前生效",
            )
            return None

        self._wuguan_guard_submitted = True
        defense = guard_defense_after_extra(state, WUGUAN_NODE_ID, extra)
        self._log(
            "武关设卡提交",
            state,
            player,
            f"{reason}；opponentETA={opponent_eta}，extraGoodFruit={extra}，预计防守值={defense}",
        )
        return WuguanTrapDecision(
            action=set_guard(WUGUAN_NODE_ID, extra_good_fruit=extra),
            stage="wuguan_guard",
        )

    def _log(self, title: str, state: GameState, player: PlayerState, detail: str) -> None:
        self._flow.important(
            "round=%s 【武关竞速｜%s】\n"
            "  我方：node=%s state=%s next=%s good=%s taskScore=%s totalScore=%s\n"
            "  阶段：luoyangEnabled=%s luoyangSubmitted=%s luoyangSeenActive=%s wuguanSubmitted=%s\n"
            "  判断：%s",
            state.round_no,
            title,
            player.current_node_id,
            player.state,
            player.next_node_id,
            player.good_fruit,
            player.task_score,
            player.total_score,
            self._enable_luoyang_stage,
            self._luoyang_guard_submitted,
            self._luoyang_guard_seen_active,
            self._wuguan_guard_submitted,
            detail,
        )
        self._logger.important(
            "wuguan_trap round=%s title=%s node=%s state=%s next=%s detail=%s",
            state.round_no,
            title,
            player.current_node_id,
            player.state,
            player.next_node_id,
            detail,
        )

    def _log_deadline(self, state: GameState, player: PlayerState, deadline: WuguanDeadline) -> None:
        if deadline.triggered_by_safety:
            result = "交付安全保护已触发，采用安全截止轮"
        elif deadline.safety_enabled:
            result = "交付安全保护已启用，但硬上限更早，采用硬上限"
        else:
            result = "交付安全保护已计算但入口关闭，采用硬上限"
        self._flow.important(
            "round=%s 【武关竞速｜交付安全截止计算】\n"
            "  我方：node=%s state=%s next=%s verified=%s\n"
            "  配置：等待硬上限=%s，交付安全保护启用=%s\n"
            "  公式：latestSafeRound = 600 - 设卡读条(%s) - 预计交付耗时(%s) - 安全余量(%s) = %s\n"
            "  结果：本轮采用武关等待截止轮=%s；%s",
            state.round_no,
            player.current_node_id,
            player.state,
            player.next_node_id,
            player.verified,
            deadline.hard_limit_round,
            deadline.safety_enabled,
            deadline.guard_process_rounds,
            deadline.delivery_estimate_rounds,
            deadline.safety_margin,
            deadline.latest_safe_round,
            deadline.selected_round,
            result,
        )
        self._logger.important(
            "wuguan_deadline_calc round=%s hard_limit=%s safety_enabled=%s delivery_estimate=%s "
            "guard_process=%s safety_margin=%s latest_safe_round=%s selected_round=%s triggered=%s",
            state.round_no,
            deadline.hard_limit_round,
            deadline.safety_enabled,
            deadline.delivery_estimate_rounds,
            deadline.guard_process_rounds,
            deadline.safety_margin,
            deadline.latest_safe_round,
            deadline.selected_round,
            deadline.triggered_by_safety,
        )
        if deadline.triggered_by_safety:
            self._flow.important(
                "round=%s 【武关竞速｜交付安全保护触发】\n"
                "  触发条件：latestSafeRound=%s 早于等待硬上限=%s\n"
                "  后续动作：本轮及之后不再继续武关等待，转入设卡后离开或直接离开主线",
                state.round_no,
                deadline.latest_safe_round,
                deadline.hard_limit_round,
            )


def opponent_wuguan_approach_status(
    state: GameState,
    player: PlayerState,
) -> WuguanApproachStatus:
    for other in state.players.values():
        if _is_own_player(other, player):
            continue
        current = other.current_node_id or ""
        next_node = other.next_node_id or ""
        if current == WUGUAN_NODE_ID:
            continue
        if next_node == WUGUAN_NODE_ID and _opponent_will_enter_wuguan(state, other, current):
            return WuguanApproachStatus(
                should_set_guard=True,
                reason=f"对手 {other.player_id} 已从 {current} 朝武关移动",
            )
        if _is_wuguan_entry_staging_node(state, other, current):
            return WuguanApproachStatus(
                should_set_guard=True,
                reason=f"对手 {other.player_id} 已到武关前置节点 {current}",
            )
        if current == LUOYANG_NODE_ID and next_node and _path_from_node_reaches_wuguan(state, other, next_node):
            return WuguanApproachStatus(
                should_set_guard=False,
                reason="",
                wait_detail=f"识别到对手 {other.player_id} 从洛阳改道 {next_node}，等待其到达武关前置节点",
            )
    return WuguanApproachStatus(
        should_set_guard=False,
        reason="",
        wait_detail="等待对手进入武关前置路径",
    )


def opponent_eta_to_node(
    state: GameState,
    player: PlayerState,
    target_node_id: str,
) -> Optional[int]:
    best: Optional[int] = None
    for other in state.players.values():
        if _is_own_player(other, player) or not other.current_node_id:
            continue
        eta = _player_eta_to_node(state, other, target_node_id)
        if eta is None:
            continue
        if best is None or eta < best:
            best = eta
    return best


def _player_eta_to_node(
    state: GameState,
    player: PlayerState,
    target_node_id: str,
) -> Optional[int]:
    if player.current_node_id == target_node_id:
        return 0
    if player.next_node_id == target_node_id and player.current_node_id:
        remaining_rounds = _route_edge_remaining_rounds(player)
        if remaining_rounds is not None:
            return remaining_rounds
        path = [player.current_node_id, target_node_id]
        return estimate_path_rounds(state, path, include_process=False)
    if not player.current_node_id:
        return None

    delivery_target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = state.game_map.fastest_path(player.current_node_id, delivery_target)
    if target_node_id not in path:
        return None
    return estimate_path_rounds(state, path[: path.index(target_node_id) + 1], include_process=True)


def _opponent_will_enter_wuguan(
    state: GameState,
    player: PlayerState,
    current_node_id: str,
) -> bool:
    if not current_node_id:
        return False
    if WUGUAN_NODE_ID not in state.game_map.neighbors(current_node_id):
        return False
    return _path_from_node_reaches_wuguan(state, player, current_node_id)


def _is_wuguan_entry_staging_node(
    state: GameState,
    player: PlayerState,
    current_node_id: str,
) -> bool:
    if not current_node_id or current_node_id == LUOYANG_NODE_ID:
        return False
    if WUGUAN_NODE_ID not in state.game_map.neighbors(current_node_id):
        return False
    return _path_from_node_reaches_wuguan(state, player, current_node_id)


def _path_from_node_reaches_wuguan(
    state: GameState,
    player: PlayerState,
    node_id: str,
) -> bool:
    if not node_id:
        return False
    target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = state.game_map.fastest_path(node_id, target)
    return WUGUAN_NODE_ID in path[1:]


def _is_own_player(other: PlayerState, player: PlayerState) -> bool:
    return other.player_id == player.player_id or other.team_id == player.team_id


def _opponent_recently_blocked_by_wuguan(state: GameState, player: PlayerState) -> bool:
    for other in state.players.values():
        if _is_own_player(other, player):
            continue
        if _player_recently_blocked_by_wuguan(state, other.player_id):
            return True
    return False


def _player_recently_blocked_by_wuguan(state: GameState, player_id: int) -> bool:
    for result in state.action_results:
        if result.get("playerId") != player_id:
            continue
        if result.get("action") != "MOVE":
            continue
        if result.get("accepted", True):
            continue
        error = str(result.get("errorCode") or result.get("result") or "")
        if error != "MOVE_BLOCKED_BY_GUARD":
            continue
        target = str(result.get("targetNodeId") or "")
        if not target or target == WUGUAN_NODE_ID:
            return True

    for event in state.events:
        if event.get("type") not in {"ACTION_REJECTED", "INVALID_ACTION"}:
            continue
        payload = event.get("payload") or {}
        if payload.get("playerId") != player_id:
            continue
        if payload.get("action") not in (None, "MOVE"):
            continue
        if payload.get("errorCode") != "MOVE_BLOCKED_BY_GUARD":
            continue
        target = str(payload.get("targetNodeId") or "")
        if not target or target == WUGUAN_NODE_ID:
            return True
    return False


def _own_wuguan_guard_removed_this_round(state: GameState, player: PlayerState) -> bool:
    for event in state.events:
        if event.get("type") not in {"GUARD_BREAK", "GUARD_INACTIVE"}:
            continue
        payload = event.get("payload") or {}
        node_id = str(payload.get("nodeId") or payload.get("targetNodeId") or "")
        if node_id != WUGUAN_NODE_ID:
            continue
        owner = str(payload.get("ownerTeamId") or payload.get("teamId") or "")
        if not owner or owner == player.team_id:
            return True
    return False


def _route_edge_remaining_rounds(player: PlayerState) -> Optional[int]:
    total = _optional_int(player.raw.get("edgeTotalMs"))
    progress = _optional_int(player.raw.get("edgeProgressMs"))
    if total is None or progress is None or total <= 0:
        return None
    remaining_ms = max(0, total - progress)
    return max(0, math.ceil(remaining_ms / 1000))


def _optional_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_delivery_slack(
    state: GameState,
    player: PlayerState,
    current: str,
    margin: int,
) -> bool:
    return state.round_no + estimate_delivery_rounds(state, current, player.verified) + margin < 600


def _wuguan_force_set_round(state: GameState, player: PlayerState) -> int:
    return _wuguan_deadline(state, player).selected_round


def _wuguan_deadline(state: GameState, player: PlayerState) -> WuguanDeadline:
    delivery_estimate_rounds = estimate_delivery_rounds(state, WUGUAN_NODE_ID, player.verified)
    latest_safe_round = (
        600
        - GUARD_PROCESS_ROUNDS
        - delivery_estimate_rounds
        - WUGUAN_DELIVERY_SAFETY_MARGIN
    )
    selected_round = (
        min(WUGUAN_FORCE_SET_ROUND, latest_safe_round)
        if WUGUAN_DELIVERY_SAFETY_LIMIT_ENABLED
        else WUGUAN_FORCE_SET_ROUND
    )
    return WuguanDeadline(
        selected_round=selected_round,
        hard_limit_round=WUGUAN_FORCE_SET_ROUND,
        safety_enabled=WUGUAN_DELIVERY_SAFETY_LIMIT_ENABLED,
        latest_safe_round=latest_safe_round,
        delivery_estimate_rounds=delivery_estimate_rounds,
        guard_process_rounds=GUARD_PROCESS_ROUNDS,
        safety_margin=WUGUAN_DELIVERY_SAFETY_MARGIN,
    )
