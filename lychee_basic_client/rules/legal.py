from lychee_basic_client.models.state import GameState


BUSY_STATES = {
    "MOVING",
    "PROCESSING",
    "CONTESTING",
    "RESTING",
    "FORCED_PASSING",
    "VERIFYING",
}


def can_submit_main_action(state: GameState) -> bool:
    player = state.me
    if player is None or player.delivered:
        return False
    return player.state not in BUSY_STATES


def can_move_to(state: GameState, target_node_id: str) -> bool:
    player = state.me
    if player is None or player.current_node_id is None:
        return False
    return target_node_id in state.game_map.neighbors(player.current_node_id)

