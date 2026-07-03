from typing import Any

from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.planning.estimates import estimate_delivery_rounds
from lychee_basic_client.protocol.actions import rush_protect, rush_speed
from lychee_basic_client.rules.buffs import has_move_buff, has_protect_buff
from lychee_basic_client.rules.states import ROUTE_EDGE_STATES
from lychee_basic_client.strategies.context import StrategyContext


class RushStrategy:
    """Conservative terminal rush-tactic use."""

    def __init__(self) -> None:
        self._logger = get_logger("strategies.rush")

    def on_start(self, state: Any) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None or player.delivered:
            return []
        if state.phase != "RUSH" or player.rush_tactic_used_count > 0:
            return []
        if player.current_node_id in {state.game_map.gate_node_id, *state.game_map.terminal_node_ids}:
            return []

        if _should_use_protect(state, player):
            self._logger.important(
                "rush_protect round=%s node=%s fresh=%s | 终局急策-护果令：30 帧内鲜度损耗 ×0.2，用于鲜度危急时保住品质分（整局仅 1 次）",
                state.round_no,
                player.current_node_id,
                player.freshness,
            )
            return [rush_protect()]

        if player.state not in ROUTE_EDGE_STATES:
            return []
        if player.good_fruit <= 2 or has_move_buff(player.raw):
            return []
        if _has_horse_inventory(player):
            return []
        if not player.current_node_id:
            return []
        if state.round_no + estimate_delivery_rounds(state, player.current_node_id, player.verified) < 520:
            return []
        self._logger.important(
            "rush_speed round=%s node=%s good=%s | 终局急策-疾行令：15 帧内基础推进量 +30%，鲜度损耗 ×1.25，用于冲刺交付（整局仅 1 次）",
            state.round_no,
            player.current_node_id,
            player.good_fruit,
        )
        return [rush_speed()]


def _should_use_protect(state: Any, player: Any) -> bool:
    if player.state != "IDLE" or player.current_process or has_protect_buff(player.raw):
        return False
    if not player.current_node_id:
        return False
    remaining = estimate_delivery_rounds(state, player.current_node_id, player.verified)
    if remaining < 18:
        return False
    if player.freshness <= 42:
        return True
    if state.weather.has_active("HOT") and player.freshness <= 62:
        return True
    return False


def _has_horse_inventory(player: Any) -> bool:
    return player.resources.get("FAST_HORSE", 0) > 0 or player.resources.get("SHORT_HORSE", 0) > 0
