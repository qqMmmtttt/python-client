from typing import Any

from lychee_basic_client.planning.estimates import estimate_delivery_rounds
from lychee_basic_client.protocol.actions import rush_speed
from lychee_basic_client.rules.buffs import has_move_buff
from lychee_basic_client.rules.states import ROUTE_EDGE_STATES
from lychee_basic_client.strategies.context import StrategyContext


class RushStrategy:
    """Conservative terminal rush-tactic use."""

    def on_start(self, state: Any) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None or player.delivered:
            return []
        if state.phase != "RUSH" or player.rush_tactic_used_count > 0:
            return []
        if player.state not in ROUTE_EDGE_STATES:
            return []
        if player.good_fruit <= 2 or has_move_buff(player.raw):
            return []
        if player.current_node_id in {state.game_map.gate_node_id, *state.game_map.terminal_node_ids}:
            return []
        if state.round_no + estimate_delivery_rounds(state, player.current_node_id, player.verified) < 520:
            return []
        return [rush_speed()]
