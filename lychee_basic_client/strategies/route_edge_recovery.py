from dataclasses import dataclass
from typing import Any, Optional

from lychee_basic_client.models.state import GameState
from lychee_basic_client.rules.states import ROUTE_EDGE_STATES
from lychee_basic_client.strategies.control import force_empty_actions


@dataclass
class RouteEdgeGuardReset:
    origin_node_id: str
    blocked_node_id: str
    pivot_node_id: str
    started_round: int
    empty_rounds: int = 0


class RouteEdgeGuardResetTracker:
    """Tracks one route-edge lane change used only to reset back to the origin node."""

    def __init__(self, logger: Any, guard_logger: Any) -> None:
        self._logger = logger
        self._guard_logger = guard_logger
        self._active: Optional[RouteEdgeGuardReset] = None

    def clear(self) -> None:
        self._active = None

    def start(
        self,
        state: GameState,
        origin_node_id: str,
        blocked_node_id: str,
        pivot_node_id: str,
    ) -> None:
        self._active = RouteEdgeGuardReset(
            origin_node_id=origin_node_id,
            blocked_node_id=blocked_node_id,
            pivot_node_id=pivot_node_id,
            started_round=state.round_no,
        )

    def force_empty_if_needed(
        self,
        state: GameState,
        player: Any,
        blocked_node_id: str,
    ) -> Optional[dict[str, Any]]:
        reset = self._active
        if reset is None or reset.blocked_node_id != blocked_node_id:
            return None

        if player.state == "IDLE" and player.current_node_id == reset.origin_node_id:
            self._logger.important(
                "guard_route_edge_reset_complete round=%s origin=%s blocked=%s pivot=%s empty_rounds=%s"
                " | 路线边设卡复位：服务端已回到起点 IDLE，后续交由节点态攻坚/通行逻辑处理",
                state.round_no,
                reset.origin_node_id,
                reset.blocked_node_id,
                reset.pivot_node_id,
                reset.empty_rounds,
            )
            self.clear()
            return None

        if (
            player.state in ROUTE_EDGE_STATES
            and player.current_node_id == reset.origin_node_id
            and player.next_node_id == reset.pivot_node_id
        ):
            reset.empty_rounds += 1
            message = (
                "【设卡处理｜换道复位空动作】\n"
                f"  位置：状态={player.state}，路线起点={reset.origin_node_id}，当前朝向={player.next_node_id}，"
                f"路线边={_raw_value(player, 'routeEdgeId')}，移动方向={_raw_value(player, 'moveDirection')}，"
                f"进度={_raw_value(player, 'edgeProgressMs')}/{_raw_value(player, 'edgeTotalMs')}\n"
                f"  关卡：被阻挡节点={reset.blocked_node_id}，换道触发节点={reset.pivot_node_id}\n"
                "  判断：已经发送过一次换道 MOVE，pivot 只用于触发服务端回到起点，不是实际目的地\n"
                "  决策：本帧强制提交 actions=[]，严禁 WAIT，严禁继续 MOVE 到换道触发节点"
            )
            self._logger.important(
                "guard_route_edge_reset_empty round=%s state=%s origin=%s blocked=%s pivot=%s empty_rounds=%s"
                " | 路线边设卡复位：已发送换道 MOVE，本帧强制提交空动作，让服务端结算回起点 IDLE，禁止继续朝 pivot 前进",
                state.round_no,
                player.state,
                reset.origin_node_id,
                reset.blocked_node_id,
                reset.pivot_node_id,
                reset.empty_rounds,
            )
            self._guard_logger.important("round=%s %s", state.round_no, message)
            return force_empty_actions(
                "ROUTE_EDGE_GUARD_RESET",
                originNodeId=reset.origin_node_id,
                blockedNodeId=reset.blocked_node_id,
                pivotNodeId=reset.pivot_node_id,
                emptyRounds=reset.empty_rounds,
            )

        if (
            player.current_node_id != reset.origin_node_id
            or player.next_node_id not in (None, reset.pivot_node_id)
        ):
            message = (
                "【设卡处理｜复位状态清理】\n"
                f"  预期：起点={reset.origin_node_id}，被阻挡节点={reset.blocked_node_id}，换道触发节点={reset.pivot_node_id}\n"
                f"  实际：状态={player.state}，当前节点={player.current_node_id}，当前朝向={player.next_node_id}\n"
                "  判断：服务端位置已脱离复位窗口，清理本次复位状态，后续重新按公开状态决策"
            )
            self._logger.important(
                "guard_route_edge_reset_abandon round=%s state=%s origin=%s blocked=%s pivot=%s current=%s next=%s"
                " | 路线边设卡复位：服务端位置已脱离复位窗口，清理复位状态",
                state.round_no,
                player.state,
                reset.origin_node_id,
                reset.blocked_node_id,
                reset.pivot_node_id,
                player.current_node_id,
                player.next_node_id,
            )
            self._guard_logger.important("round=%s %s", state.round_no, message)
            self.clear()
        return None

    def complete_if_idle(self, state: GameState, player: Any) -> None:
        reset = self._active
        if reset is None:
            return
        if player.state != "IDLE" or player.current_node_id != reset.origin_node_id:
            return
        message = (
            "【设卡处理｜复位完成】\n"
            f"  位置：状态=IDLE，当前节点={player.current_node_id}\n"
            f"  关卡：被阻挡节点={reset.blocked_node_id}，换道触发节点={reset.pivot_node_id}\n"
            "  判断：车队已回到起点节点，下一步交给节点态攻坚逻辑处理\n"
            "  决策：清理复位状态，允许 BREAK_GUARD / SQUAD_WEAKEN / FORCED_PASS 等节点态策略"
        )
        self._logger.important(
            "guard_route_edge_reset_complete round=%s origin=%s blocked=%s pivot=%s empty_rounds=%s"
            " | 路线边设卡复位：服务端已回到起点 IDLE，后续交由节点态攻坚/通行逻辑处理",
            state.round_no,
            reset.origin_node_id,
            reset.blocked_node_id,
            reset.pivot_node_id,
            reset.empty_rounds,
        )
        self._guard_logger.important("round=%s %s", state.round_no, message)
        self.clear()


def _raw_value(player: Any, key: str) -> Any:
    try:
        return player.raw.get(key)
    except AttributeError:
        return None
