from typing import Any

from lychee_basic_client.models.state import GameState
from lychee_basic_client.protocol.actions import claim_resource, use_resource

USEFUL_PICKUPS = ("FAST_HORSE", "SHORT_HORSE", "ICE_BOX")
BUSY_STATES = {"PROCESSING", "CONTESTING", "RESTING", "FORCED_PASSING", "VERIFYING"}


class ResourceStrategy:
    """Resource pickup and inventory-use decisions."""

    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        player = state.me
        if player is None or player.delivered or player.state in BUSY_STATES:
            return []

        if player.freshness and player.freshness < 75 and player.resources.get("ICE_BOX", 0) > 0:
            return [use_resource("ICE_BOX")]

        if player.state in {"IDLE", "MOVING", "WAITING"}:
            if player.resources.get("FAST_HORSE", 0) > 0 and not _has_move_buff(player.raw):
                return [use_resource("FAST_HORSE")]
            if player.resources.get("SHORT_HORSE", 0) > 0 and not _has_move_buff(player.raw):
                return [use_resource("SHORT_HORSE")]

        if player.state == "IDLE" and player.current_node_id and state.round_no < 360:
            node = state.nodes.get(player.current_node_id)
            if node:
                for resource_type in USEFUL_PICKUPS:
                    if node.resource_stock.get(resource_type, 0) > 0:
                        return [claim_resource(player.current_node_id, resource_type)]
        return []


def _has_move_buff(raw_player: dict[str, Any]) -> bool:
    for buff in raw_player.get("buffs") or []:
        if buff.get("type") in {"FAST_HORSE", "SHORT_HORSE", "RUSH_SPEED"}:
            return True
    return False
