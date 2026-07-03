from dataclasses import dataclass
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
    wait,
)
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.rules.states import NODE_BUSY_STATES, ROUTE_EDGE_STATES
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.strategies.routing import RoutePolicy


class DeliveryStrategy:
    """End-to-end S14 verification and S15 delivery decisions."""

    def __init__(self, route_policy: RoutePolicy) -> None:
        self._route_policy = route_policy
        self._logger = get_logger("strategies.delivery")
        self._completed_process_nodes: set[str] = set()
        self._pending_process_node: Optional[str] = None
        self._last_settled_node: Optional[str] = None
        self._rejected_task_ids: set[str] = set()
        self._object_busy_nodes: set[str] = set()
        self._object_busy_recover_round: int = 0
        self._blocked_move_targets: set[str] = set()
        self._guard_blocked_move_targets: set[str] = set()
        self._guard_blocked_rounds: dict[str, int] = {}
        self._obstacle_blocked_move_targets: set[str] = set()
        self._route_edge_resume_targets: set[str] = set()
        self._last_move_target: Optional[str] = None

    def on_start(self, state: GameState) -> None:
        self._completed_process_nodes.clear()
        self._pending_process_node = None
        self._last_settled_node = None
        self._rejected_task_ids.clear()
        self._object_busy_nodes.clear()
        self._object_busy_recover_round = 0
        self._blocked_move_targets.clear()
        self._guard_blocked_move_targets.clear()
        self._guard_blocked_rounds.clear()
        self._obstacle_blocked_move_targets.clear()
        self._route_edge_resume_targets.clear()
        self._last_move_target = None
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        self._observe_process_completion(context)

        player = state.me
        if player is None or player.delivered:
            return []
        if player.current_process:
            return []
        if player.state in NODE_BUSY_STATES:
            return []

        if player.state in ROUTE_EDGE_STATES:
            return self._decide_while_moving(state, player)

        if player.state != "IDLE":
            return []

        if not player.current_node_id:
            return []

        current = player.current_node_id
        gate = state.game_map.gate_node_id
        terminal = state.game_map.terminal_node_ids[0]
        self._observe_new_settled_node(state, current)

        if current == terminal:
            if player.verified and player.good_fruit > 0 and player.freshness > 0:
                self._logger.important(
                    "deliver round=%s node=%s good=%s fresh=%s score=%s | 终点交付：满足交付条件，提交 DELIVER 完成本局交付",
                    state.round_no,
                    current,
                    player.good_fruit,
                    player.freshness,
                    player.total_score,
                )
                return [deliver()]
            if not player.verified:
                next_node = self._route_policy.next_hop(state, current, gate)
                return [self._move(next_node)] if next_node else []
            return []

        if current == gate:
            if not player.verified:
                if state.phase == "RUSH":
                    rush_tactic = "BREAK_ORDER" if _should_bind_break_order_to_verify(state) else None
                    self._logger.important(
                        "verify_gate round=%s node=%s break_order=%s | 宫门验核：宫宴冲刺阶段，提交 VERIFY_GATE 启动宫门验核流程（6 帧处理）",
                        state.round_no,
                        current,
                        rush_tactic,
                    )
                    return [verify_gate(gate, rush_tactic=rush_tactic)]
                return []
            return [self._move(terminal)]

        process_action = self._process_action_if_needed(state, current)
        if process_action:
            return [process_action]

        mandatory_target = self._mandatory_process_target(state, current)
        if mandatory_target is not None:
            next_node = self._route_policy.next_hop(state, current, mandatory_target)
            return [self._move(next_node)] if next_node else []

        profile_action = self._mandatory_profile_action_if_needed(state, current, gate)
        if profile_action:
            return [profile_action]

        adjacent_guard_decision = self._adjacent_blocked_guard_decision_if_needed(
            state,
            current,
        )
        if adjacent_guard_decision is not None:
            return [adjacent_guard_decision.action] if adjacent_guard_decision.action else []

        task_target = select_task_target(state, current, self._rejected_task_ids)
        if task_target is not None and task_target.stand_node_id == current:
            return [claim_task(task_target.task_id)]
        target = task_target.stand_node_id if task_target is not None else gate
        if player.verified:
            target = terminal
        next_node = self._route_policy.next_hop(state, current, target)
        if next_node is None:
            return []

        blocking_decision = self._blocking_decision_if_needed(state, next_node)
        if blocking_decision is not None:
            self._logger.important(
                "main_path_blocked round=%s current=%s next=%s target=%s action=%s"
                " | 主交付路径下一节点存在阻挡（设卡/障碍），采用阻挡决策；若 action 为空则本帧等待",
                state.round_no,
                current,
                next_node,
                target,
                blocking_decision.action,
            )
            return [blocking_decision.action] if blocking_decision.action else []

        return [self._move(next_node)]

    def _decide_while_moving(
        self, state: GameState, player: Any
    ) -> list[dict[str, Any]]:
        if player.next_node_id:
            recovery_target = self._route_edge_guard_recovery_target(
                state,
                player.current_node_id,
                player.next_node_id,
            )
            if recovery_target:
                if not self._route_edge_target_blocked_by_guard(state, recovery_target):
                    self._discard_blocked_target(recovery_target)
                    self._logger.important(
                        "guard_cleared_route_edge_resume round=%s state=%s from=%s current_next=%s target=%s"
                        " | 路线边移动中：原阻挡设卡已清除，恢复前往目标节点",
                        state.round_no,
                        player.state,
                        player.current_node_id,
                        player.next_node_id,
                        recovery_target,
                    )
                    return [self._move(recovery_target)]

                if player.next_node_id != recovery_target:
                    staging_target = self._route_edge_reset_pivot_target(
                        state,
                        player.current_node_id,
                        recovery_target,
                        player.next_node_id,
                    )
                    if staging_target and staging_target != player.next_node_id:
                        self._logger.important(
                            "guard_blocked_route_edge_restage round=%s state=%s from=%s blocked=%s current_next=%s staging=%s"
                            " | 路线边移动中：当前改道目标不是最佳攻坚 staging，改道到可支撑后续攻坚的相邻节点",
                            state.round_no,
                            player.state,
                            player.current_node_id,
                            recovery_target,
                            player.next_node_id,
                            staging_target,
                        )
                        return [self._move(staging_target)]
                    if _should_hold_for_route_edge_guard_recovery(
                        state, recovery_target
                    ):
                        self._logger.important(
                            "guard_blocked_route_edge_hold round=%s state=%s from=%s blocked=%s current_next=%s action=WAIT reason=await_squad"
                            " | 路线边移动中：目标节点仍被设卡阻挡且小分队仍可能削弱，本帧主动 WAIT 等待小分队结算事件",
                            state.round_no,
                            player.state,
                            player.current_node_id,
                            recovery_target,
                            player.next_node_id,
                        )
                        return [wait()]
                    if player.next_node_id:
                        self._logger.important(
                            "guard_blocked_route_edge_continue_staging round=%s state=%s from=%s blocked=%s current_next=%s reason=no_squad"
                            " | 路线边移动中：无可用/在途小分队，继续到 staging 节点以恢复节点态，再由主车队攻坚",
                            state.round_no,
                            player.state,
                            player.current_node_id,
                            recovery_target,
                            player.next_node_id,
                        )
                        return [self._move(player.next_node_id)]
                    return []

                pivot_target = self._route_edge_reset_pivot_target(
                    state,
                    player.current_node_id,
                    recovery_target,
                    player.next_node_id,
                )
                if pivot_target:
                    self._logger.important(
                        "guard_blocked_route_edge_reset round=%s state=%s from=%s blocked=%s current_next=%s pivot=%s"
                        " | 路线边移动中：目标被设卡阻挡，改道前往绕行枢纽节点",
                        state.round_no,
                        player.state,
                        player.current_node_id,
                        recovery_target,
                        player.next_node_id,
                        pivot_target,
                    )
                    return [self._move(pivot_target)]
                self._logger.important(
                    "guard_blocked_on_route_edge_no_pivot round=%s state=%s from=%s to=%s action=MOVE_ONLY"
                    " | 路线边移动中：目标被设卡阻挡且无绕行枢纽，仍提交向目标移动",
                    state.round_no,
                    player.state,
                    player.current_node_id,
                    player.next_node_id,
                )
            return [self._move(player.next_node_id)]
        return []

    def _move(self, target_node_id: str) -> dict[str, Any]:
        self._last_move_target = target_node_id
        return move(target_node_id)

    def _process_action_if_needed(
        self, state: GameState, current: str
    ) -> Optional[dict[str, Any]]:
        if current in self._completed_process_nodes:
            return None
        if current in self._object_busy_nodes:
            if state.round_no < self._object_busy_recover_round:
                self._completed_process_nodes.add(current)
                return None
            self._object_busy_nodes.discard(current)
        process_node = state.game_map.process_node(current)
        if process_node is None or process_node.process_type == "VERIFY":
            return None

        self._pending_process_node = current
        self._logger.important(
            "process_start round=%s node=%s type=%s process_round=%s | 固定处理：主车队到达处理站点，提交 PROCESS 启动固定流程（完成前不能离站）",
            state.round_no,
            current,
            process_node.process_type,
            process_node.process_round,
        )
        return process(current)

    def _blocking_decision_if_needed(
        self, state: GameState, target_node_id: str
    ) -> Optional["_BlockingDecision"]:
        player = state.me
        if player is None:
            return None
        node = state.nodes.get(target_node_id)
        if node is None:
            if target_node_id in self._guard_blocked_move_targets:
                return self._unknown_guard_action(state, target_node_id)
            if target_node_id in self._blocked_move_targets:
                self._logger.important(
                    "unknown_blocked_forced_pass round=%s target=%s | 节点状态未知且曾记录阻挡，直接提交 FORCED_PASS 强制通行",
                    state.round_no,
                    target_node_id,
                )
                return _BlockingDecision(forced_pass(target_node_id))
            return None

        if node.has_obstacle:
            t04 = find_t04_for_obstacle(state, target_node_id, self._rejected_task_ids)
            if t04 is not None and _has_delivery_slack(state, target_node_id, margin=80):
                self._logger.important(
                    "obstacle_t04_claim round=%s target=%s task=%s | 道路障碍：存在对应 T04 清障任务，提交 CLAIM_TASK 兼顾清障与得分（30 分）",
                    state.round_no,
                    target_node_id,
                    t04.get("taskId"),
                )
                return _BlockingDecision(claim_task(t04["taskId"]))
            if _should_clear_obstacle(state, target_node_id):
                self._logger.important(
                    "obstacle_clear round=%s target=%s | 道路障碍：无对应 T04，提交 CLEAR 主车队清障（6 帧处理，消耗 1 篓好果）",
                    state.round_no,
                    target_node_id,
                )
                return _BlockingDecision(clear(target_node_id))
            self._logger.important(
                "obstacle_forced_pass round=%s target=%s | 道路障碍：不宜清障，提交 FORCED_PASS 强制通行（8 帧时间税，不清除障碍）",
                state.round_no,
                target_node_id,
            )
            return _BlockingDecision(forced_pass(target_node_id))

        guard = enemy_guard_at(node, player)
        if guard is not None:
            return self._enemy_guard_action(state, target_node_id, guard.defense)

        self._discard_blocked_target(target_node_id)
        return None

    def _adjacent_blocked_guard_decision_if_needed(
        self,
        state: GameState,
        current_node_id: str,
    ) -> Optional["_BlockingDecision"]:
        for target_node_id in self._adjacent_guard_targets(state, current_node_id):
            if target_node_id not in state.game_map.neighbors(current_node_id):
                continue
            decision = self._blocking_decision_if_needed(state, target_node_id)
            if decision is None:
                continue
            self._logger.important(
                "guard_blocked_adjacent_recovery round=%s current=%s target=%s action=%s"
                " | 停靠节点：检测到相邻节点存在敌方设卡阻挡，主动尝试攻坚或通行",
                state.round_no,
                current_node_id,
                target_node_id,
                decision.action,
            )
            return decision
        return None

    def _adjacent_guard_targets(
        self,
        state: GameState,
        current_node_id: str,
    ) -> list[str]:
        candidates = set(self._guard_blocked_move_targets)
        delivery_target = (
            state.game_map.terminal_node_ids[0]
            if state.me and state.me.verified
            else state.game_map.gate_node_id
        )
        path = state.game_map.fastest_path(current_node_id, delivery_target)
        if len(path) >= 2:
            next_node_id = path[1]
            if enemy_guard_at(state.nodes.get(next_node_id), state.me) is not None:
                candidates.add(next_node_id)
                self._remember_guard_block(state, next_node_id)
        return sorted(candidates)

    def _route_edge_guard_recovery_target(
        self,
        state: GameState,
        origin_node_id: Optional[str],
        current_next_node_id: Optional[str],
    ) -> Optional[str]:
        if not origin_node_id:
            return None
        neighbors = set(state.game_map.neighbors(origin_node_id))
        if (
            current_next_node_id
            and current_next_node_id in neighbors
            and self._route_edge_target_blocked_by_guard(state, current_next_node_id)
        ):
            return current_next_node_id

        for target_node_id in sorted(self._guard_blocked_move_targets):
            if target_node_id in neighbors:
                return target_node_id
        for target_node_id in sorted(self._route_edge_resume_targets):
            if target_node_id in neighbors:
                return target_node_id
        return None

    def _route_edge_target_blocked_by_guard(
        self,
        state: GameState,
        target_node_id: str,
    ) -> bool:
        node = state.nodes.get(target_node_id)
        if enemy_guard_at(node, state.me) is not None:
            self._remember_guard_block(state, target_node_id)
            return True
        if (
            target_node_id in self._guard_blocked_move_targets
            and self._guard_blocked_rounds.get(target_node_id) == state.round_no
        ):
            return True
        if node is not None:
            self._discard_guard_block(target_node_id)
            return False
        return target_node_id in self._guard_blocked_move_targets

    def _route_edge_reset_pivot_target(
        self,
        state: GameState,
        origin_node_id: Optional[str],
        blocked_target_node_id: str,
        current_next_node_id: Optional[str],
    ) -> Optional[str]:
        if not origin_node_id:
            return None

        candidates = [
            node_id
            for node_id in state.game_map.neighbors(origin_node_id)
            if node_id != blocked_target_node_id
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda node_id: _pivot_score(
                state, origin_node_id, node_id, blocked_target_node_id
            ),
        )

    def _enemy_guard_action(
        self,
        state: GameState,
        target_node_id: str,
        defense: int,
    ) -> "_BlockingDecision":
        player = state.me
        self._logger.important(
            "guard_detected round=%s target=%s defense=%s good=%s bad=%s squad_avail=%s squad_in_flight=%s phase=%s break_order_ready=%s slack=%s"
            " | 检测到目标节点存在敌方设卡，进入攻坚决策路径：按 直接攻坚→破关令攻坚→等待小分队削弱→部分削弱→强制通行 顺序评估",
            state.round_no,
            target_node_id,
            defense,
            player.good_fruit if player else None,
            player.bad_fruit if player else None,
            player.squad_available if player else None,
            _squad_in_flight(player),
            state.phase,
            player.break_order_ready if player else None,
            _has_delivery_slack(state, target_node_id, margin=18),
        )
        payment = _break_guard_payment(state, defense)
        if (
            payment is not None
            and _has_delivery_slack(state, target_node_id, margin=18)
        ):
            self._logger.important(
                "guard_break round=%s target=%s defense=%s payment=%s mode=direct"
                " | 攻坚破卡(直接)：果品组合攻坚值≥防守值且交付时间充裕(余量≥18帧)，可一击破卡（好果每篓+2，坏果每篓+3 攻坚值）",
                state.round_no,
                target_node_id,
                defense,
                payment,
            )
            return _BlockingDecision(break_guard(target_node_id, **payment))
        break_order_payment = _break_guard_payment_with_break_order(state, defense)
        if (
            break_order_payment is not None
            and _has_delivery_slack(state, target_node_id, margin=18)
        ):
            self._logger.important(
                "guard_break round=%s target=%s defense=%s payment=%s mode=break_order"
                " | 攻坚破卡(破关令)：直接攻坚果品不足，破关令补+3攻坚值后可一击破卡（终局急策额度消耗1次）",
                state.round_no,
                target_node_id,
                defense,
                break_order_payment,
            )
            return _BlockingDecision(
                break_guard(
                    target_node_id,
                    **break_order_payment,
                    rush_tactic="BREAK_ORDER",
                )
            )
        if _should_hold_for_squad_weaken(state, defense):
            self._logger.important(
                "guard_hold_for_squad round=%s target=%s defense=%s squad_available=%s squad_in_flight=%s"
                " | 暂不攻坚：直接/破关令攻坚均不可行，非冲刺阶段且小分队可用，等待小分队削弱设卡后再行突破",
                state.round_no,
                target_node_id,
                defense,
                state.me.squad_available if state.me else None,
                _squad_in_flight(state.me),
            )
            return _BlockingDecision(None)
        partial_payment = _partial_break_guard_payment(state)
        if partial_payment is not None:
            self._logger.important(
                "guard_break round=%s target=%s defense=%s payment=%s mode=partial"
                " | 攻坚破卡(部分削弱)：无法一击破卡且无小分队可用，投入部分果品削弱设卡防守值（攻坚失败将休整5帧）",
                state.round_no,
                target_node_id,
                defense,
                partial_payment,
            )
            return _BlockingDecision(break_guard(target_node_id, **partial_payment))
        self._logger.important(
            "guard_forced_pass round=%s target=%s defense=%s reason=no_break_payment"
            " | 强制通行：无果品攻坚且无小分队可用，改为强制通行突破敌方设卡（不清除设卡，按防守值支付时间税）",
            state.round_no,
            target_node_id,
            defense,
        )
        return _BlockingDecision(forced_pass(target_node_id))

    def _unknown_guard_action(
        self,
        state: GameState,
        target_node_id: str,
    ) -> "_BlockingDecision":
        defense_cap = _guard_defense_cap(state, target_node_id)
        player = state.me
        self._logger.important(
            "guard_detected_unknown round=%s target=%s defense_cap=%s good=%s bad=%s squad_avail=%s phase=%s break_order_ready=%s slack=%s"
            " | 目标节点状态未知（已离开视野），按防守值上限估算进入攻坚决策路径：直接攻坚→破关令攻坚→等待小分队→部分削弱→强制通行",
            state.round_no,
            target_node_id,
            defense_cap,
            player.good_fruit if player else None,
            player.bad_fruit if player else None,
            player.squad_available if player else None,
            state.phase,
            player.break_order_ready if player else None,
            _has_delivery_slack(state, target_node_id, margin=18),
        )
        payment = _break_guard_payment(state, defense_cap)
        if (
            payment is not None
            and _has_delivery_slack(state, target_node_id, margin=18)
        ):
            self._logger.important(
                "guard_break_unknown round=%s target=%s defense_cap=%s payment=%s mode=direct"
                " | 未知节点攻坚(直接)：按估算防守值，果品组合可一击破卡且交付时间充裕",
                state.round_no,
                target_node_id,
                defense_cap,
                payment,
            )
            return _BlockingDecision(break_guard(target_node_id, **payment))
        break_order_payment = _break_guard_payment_with_break_order(state, defense_cap)
        if (
            break_order_payment is not None
            and _has_delivery_slack(state, target_node_id, margin=18)
        ):
            self._logger.important(
                "guard_break_unknown round=%s target=%s defense_cap=%s payment=%s mode=break_order"
                " | 未知节点攻坚(破关令)：直接攻坚果品不足，破关令补+3后可一击破卡",
                state.round_no,
                target_node_id,
                defense_cap,
                break_order_payment,
            )
            return _BlockingDecision(
                break_guard(
                    target_node_id,
                    **break_order_payment,
                    rush_tactic="BREAK_ORDER",
                )
            )
        if _should_hold_for_squad_weaken(state, defense_cap):
            self._logger.important(
                "guard_hold_for_squad_unknown round=%s target=%s defense_cap=%s squad_available=%s squad_in_flight=%s"
                " | 未知节点暂不攻坚：直接/破关令均不可行，非冲刺阶段且小分队可用，等待削弱后再行突破",
                state.round_no,
                target_node_id,
                defense_cap,
                state.me.squad_available if state.me else None,
                _squad_in_flight(state.me),
            )
            return _BlockingDecision(None)
        partial_payment = _partial_break_guard_payment(state)
        if partial_payment is not None:
            self._logger.important(
                "guard_break_unknown round=%s target=%s defense_cap=%s payment=%s mode=partial"
                " | 未知节点部分削弱：无法一击破卡且无小分队，投入部分果品削弱估算防守值（失败休整5帧）",
                state.round_no,
                target_node_id,
                defense_cap,
                partial_payment,
            )
            return _BlockingDecision(break_guard(target_node_id, **partial_payment))
        self._logger.important(
            "guard_forced_pass_unknown round=%s target=%s defense_cap=%s"
            " | 未知节点强制通行：无果品攻坚且无小分队可用，按估算防守值强制通行突破",
            state.round_no,
            target_node_id,
            defense_cap,
        )
        return _BlockingDecision(forced_pass(target_node_id))

    def _observe_process_completion(self, context: StrategyContext) -> None:
        state = context.state
        player = state.me
        if player is None:
            return

        for node_id in context.events.completed_process_nodes:
            self._completed_process_nodes.add(node_id)
            self._object_busy_nodes.discard(node_id)
            if self._pending_process_node == node_id:
                self._pending_process_node = None

        for event in state.events:
            target_node_id = _cleared_guard_target_from_event(event, state.player_id)
            if target_node_id:
                self._blocked_move_targets.discard(target_node_id)
                self._discard_guard_block(target_node_id)
                self._obstacle_blocked_move_targets.discard(target_node_id)
                self._route_edge_resume_targets.add(target_node_id)

        for rejected in context.events.rejected_actions:
            if rejected.action in {"PROCESS", "DOCK"} and self._pending_process_node:
                if rejected.error_code == "OBJECT_BUSY":
                    self._object_busy_nodes.add(self._pending_process_node)
                    self._object_busy_recover_round = state.round_no + 6
                self._pending_process_node = None
            if rejected.error_code == "PROCESS_REQUIRED" and player.current_node_id:
                self._completed_process_nodes.discard(player.current_node_id)
            if rejected.action == "CLAIM_TASK":
                task_id = _rejected_task_id(rejected.raw)
                if task_id:
                    self._rejected_task_ids.add(task_id)
            if rejected.error_code in {
                "MOVE_BLOCKED_BY_GUARD",
                "MOVE_BLOCKED_BY_OBSTACLE",
                "BLOCKED",
            }:
                target_node_id = (
                    _rejected_target_node(rejected.raw)
                    or player.next_node_id
                    or self._last_move_target
                    or ""
                )
                if target_node_id:
                    self._blocked_move_targets.add(target_node_id)
                    if rejected.error_code == "MOVE_BLOCKED_BY_GUARD":
                        self._remember_guard_block(state, target_node_id)
                        self._logger.important(
                            "move_blocked_by_guard round=%s target=%s | 上帧移动被敌方设卡拒绝，记录阻挡节点，后续将进入攻坚/绕行决策路径",
                            state.round_no,
                            target_node_id,
                        )
                    elif rejected.error_code == "MOVE_BLOCKED_BY_OBSTACLE":
                        self._obstacle_blocked_move_targets.add(target_node_id)
                        self._logger.important(
                            "move_blocked_by_obstacle round=%s target=%s | 上帧移动被道路障碍拒绝，记录阻挡节点，后续将进入清障/强制通行决策路径",
                            state.round_no,
                            target_node_id,
                        )

    def _observe_new_settled_node(self, state: GameState, current: str) -> None:
        if current == self._last_settled_node:
            return
        self._last_settled_node = current
        process_node = state.game_map.process_node(current)
        if process_node is not None and process_node.process_type != "VERIFY":
            self._completed_process_nodes.discard(current)

    def _discard_blocked_target(self, target_node_id: str) -> None:
        self._blocked_move_targets.discard(target_node_id)
        self._discard_guard_block(target_node_id)
        self._obstacle_blocked_move_targets.discard(target_node_id)
        self._route_edge_resume_targets.discard(target_node_id)

    def _remember_guard_block(self, state: GameState, target_node_id: str) -> None:
        self._guard_blocked_move_targets.add(target_node_id)
        self._guard_blocked_rounds[target_node_id] = state.round_no

    def _discard_guard_block(self, target_node_id: str) -> None:
        self._guard_blocked_move_targets.discard(target_node_id)
        self._guard_blocked_rounds.pop(target_node_id, None)

    def _mandatory_process_target(self, state: GameState, current: str) -> Optional[str]:
        initial_transfer = "S02"
        if initial_transfer not in state.game_map.process_nodes:
            return None
        if initial_transfer in self._completed_process_nodes:
            return None
        if initial_transfer in self._object_busy_nodes:
            return None
        if current == state.game_map.start_node_id:
            return initial_transfer
        return None

    def _mandatory_profile_action_if_needed(
        self, state: GameState, current: str, gate: str
    ) -> Optional[dict[str, Any]]:
        if current not in {"S02", "S04", "S05"}:
            return None
        next_node = self._route_policy.profile_next_hop(state, current, gate)
        if next_node is None:
            return None
        blocking_decision = self._blocking_decision_if_needed(state, next_node)
        if blocking_decision is not None:
            self._logger.important(
                "mandatory_profile_blocked round=%s current=%s next=%s action=%s"
                " | 强制路径(S02/S04/S05)下一节点存在阻挡，采用阻挡决策（设卡攻坚或障碍处理）",
                state.round_no,
                current,
                next_node,
                blocking_decision.action,
            )
            return blocking_decision.action
        return self._move(next_node)


@dataclass(frozen=True)
class _BlockingDecision:
    action: Optional[dict[str, Any]]


def _should_bind_break_order_to_verify(state: GameState) -> bool:
    player = state.me
    if player is None:
        return False
    if not _can_bind_break_order(state):
        return False
    if player.bad_fruit >= 2:
        return True
    return state.round_no + estimate_delivery_rounds(state, state.game_map.gate_node_id, False) >= 570


def _has_delivery_slack(state: GameState, from_node_id: str, margin: int) -> bool:
    player = state.me
    if player is None:
        return False
    return state.round_no + estimate_delivery_rounds(state, from_node_id, player.verified) + margin < 600


def _should_clear_obstacle(state: GameState, target_node_id: str) -> bool:
    player = state.me
    if player is None or player.good_fruit <= 1:
        return False
    if state.round_no >= 430:
        return False
    return _has_delivery_slack(state, target_node_id, margin=55)


def _guard_defense_cap(state: GameState, target_node_id: str) -> int:
    runtime_node = state.nodes.get(target_node_id)
    if runtime_node is not None and runtime_node.has_obstacle:
        return 5
    if target_node_id == state.game_map.gate_node_id:
        return 4
    map_node = state.game_map.nodes.get(target_node_id)
    node_type = str(
        (map_node.raw if map_node else {}).get("nodeType")
        or (map_node.raw if map_node else {}).get("type")
        or ""
    ).upper()
    if node_type == "KEY_PASS":
        return 7
    return 6


def _break_guard_payment(state: GameState, defense: int) -> Optional[dict[str, int]]:
    player = state.me
    if player is None or defense <= 0:
        return None

    max_bad = min(2, player.bad_fruit)
    max_good = min(2, max(0, player.good_fruit - 1))
    best: Optional[tuple[int, int, int]] = None
    for bad_fruit in range(max_bad + 1):
        for good_fruit in range(max_good + 1):
            attack = bad_fruit * 3 + good_fruit * 2
            if attack < defense:
                continue
            candidate = (good_fruit, bad_fruit + good_fruit, bad_fruit)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return None
    good_fruit, _, bad_fruit = best
    return {"good_fruit": good_fruit, "bad_fruit": bad_fruit}


def _partial_break_guard_payment(state: GameState) -> Optional[dict[str, int]]:
    player = state.me
    if player is None:
        return None
    bad_fruit = min(2, player.bad_fruit)
    good_fruit = min(2, max(0, player.good_fruit - 1))
    if bad_fruit <= 0 and good_fruit <= 0:
        return None
    return {"good_fruit": good_fruit, "bad_fruit": bad_fruit}


def _break_guard_payment_with_break_order(
    state: GameState,
    defense: int,
) -> Optional[dict[str, int]]:
    player = state.me
    if player is None or defense <= 0 or not _can_bind_break_order(state):
        return None

    break_order_good_cost, break_order_bad_cost = _break_order_cost(player)
    available_good = player.good_fruit - break_order_good_cost
    available_bad = player.bad_fruit - break_order_bad_cost
    if available_good <= 0 or available_bad < 0:
        return None

    max_bad = min(2, available_bad)
    max_good = min(2, max(0, available_good - 1))
    best: Optional[tuple[int, int, int]] = None
    for bad_fruit in range(max_bad + 1):
        for good_fruit in range(max_good + 1):
            attack = 3 + bad_fruit * 3 + good_fruit * 2
            if attack < defense:
                continue
            candidate = (good_fruit, bad_fruit + good_fruit, bad_fruit)
            if best is None or candidate < best:
                best = candidate
    if best is None:
        return None
    good_fruit, _, bad_fruit = best
    return {"good_fruit": good_fruit, "bad_fruit": bad_fruit}


def _can_bind_break_order(state: GameState) -> bool:
    player = state.me
    if player is None:
        return False
    if state.phase != "RUSH" or player.rush_tactic_used_count > 0:
        return False
    if not player.break_order_ready:
        return False
    if player.bad_fruit >= 2:
        return True
    return player.good_fruit > 1


def _should_hold_for_squad_weaken(state: GameState, defense: int) -> bool:
    player = state.me
    if player is None or defense <= 0 or state.phase == "RUSH":
        return False
    if player.squad_available >= 2:
        return True
    return _squad_in_flight(player) > 0


def _should_hold_for_route_edge_guard_recovery(
    state: GameState,
    target_node_id: str,
) -> bool:
    player = state.me
    if player is None or state.phase == "RUSH":
        return False
    node = state.nodes.get(target_node_id)
    guard = enemy_guard_at(node, player)
    if guard is None:
        return False
    return player.squad_available >= 2 or _squad_in_flight(player) > 0


def _squad_in_flight(player: Any) -> int:
    if player is None:
        return 0
    try:
        return int(player.raw.get("squadInFlight") or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def _pivot_score(
    state: GameState,
    origin_node_id: str,
    candidate_node_id: str,
    blocked_target_node_id: str,
) -> tuple[int, int, int, int, str]:
    node = state.nodes.get(candidate_node_id)
    block_penalty = 0
    if enemy_guard_at(node, state.me) is not None:
        block_penalty = 2
    elif node is not None and node.has_obstacle:
        block_penalty = 1
    staging_penalty = (
        0
        if blocked_target_node_id in state.game_map.neighbors(candidate_node_id)
        else 1
    )
    return (
        block_penalty,
        staging_penalty,
        _path_distance(state, candidate_node_id, blocked_target_node_id),
        _edge_distance(state, origin_node_id, candidate_node_id),
        candidate_node_id,
    )


def _path_distance(state: GameState, start_node_id: str, target_node_id: str) -> int:
    path = state.game_map.fastest_path(start_node_id, target_node_id)
    if not path:
        return 1_000_000
    total = 0
    for left, right in zip(path, path[1:]):
        total += _edge_distance(state, left, right)
    return total


def _edge_distance(state: GameState, left: str, right: str) -> int:
    for edge, neighbor in state.game_map.iter_neighbor_edges(left):
        if neighbor == right:
            return edge.distance
    return 1_000_000


def _cleared_guard_target_from_event(event: dict[str, Any], player_id: int) -> str:
    event_type = str(event.get("type") or "")
    payload = event.get("payload") or {}
    target_node_id = str(payload.get("targetNodeId") or payload.get("nodeId") or "")
    if not target_node_id:
        return ""

    event_player_id = payload.get("playerId")
    if event_type in {"SQUAD_WEAKEN", "GUARD_BREAK"} and event_player_id not in (None, player_id):
        return ""

    if event_type == "SQUAD_WEAKEN" and "after" in payload and _event_int(payload.get("after")) <= 0:
        return target_node_id
    if event_type == "GUARD_BREAK":
        if payload.get("success") is True:
            return target_node_id
        if "after" in payload and _event_int(payload.get("after")) <= 0:
            return target_node_id
    if event_type in {"GUARD_INACTIVE", "GUARD_WEATHERING"}:
        if "after" not in payload or _event_int(payload.get("after")) <= 0:
            return target_node_id
    return ""


def _event_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _break_order_cost(player: Any) -> tuple[int, int]:
    if player.bad_fruit >= 2:
        return 0, 2
    return 1, 0


def _rejected_task_id(raw: dict[str, Any]) -> str:
    payload = raw.get("payload") or raw
    return str(payload.get("taskId") or "")


def _rejected_target_node(raw: dict[str, Any]) -> str:
    payload = raw.get("payload") or raw
    return str(payload.get("targetNodeId") or payload.get("nodeId") or "")
