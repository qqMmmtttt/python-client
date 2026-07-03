from typing import Any, Optional

from lychee_basic_client.models.state import GameState, NodeState, PlayerState
from lychee_basic_client.planning.estimates import estimate_delivery_rounds, estimate_path_rounds
from lychee_basic_client.planning.tasks import TASK_SCORE_GOAL
from lychee_basic_client.protocol.actions import set_guard
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.strategies.context import StrategyContext


KEY_GUARD_NODES = {
    "S10": 120,
    "S11": 92,
    "S14": 88,
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
MAX_ACTIVE_OWN_GUARDS = 2


class GuardStrategy:
    """Conservative guard placement after the scoring base is safe."""

    def __init__(self) -> None:
        self._attempted_nodes: set[str] = set()

    def on_start(self, state: Any) -> None:
        self._attempted_nodes.clear()
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None or player.delivered:
            return []
        if state.phase == "RUSH" or player.state != "IDLE" or player.current_process:
            return []

        current = player.current_node_id
        if not current or current in self._attempted_nodes:
            return []
        if player.task_score < TASK_SCORE_GOAL:
            return []
        if state.round_no >= 420:
            return []
        if _active_own_guard_count(state, player) >= MAX_ACTIVE_OWN_GUARDS:
            return []

        node = state.nodes.get(current)
        if node is None:
            return []
        if _has_active_guard(node) or enemy_guard_at(node, player) is not None:
            return []

        candidate_score = _guard_candidate_score(state, current)
        if candidate_score < MIN_GUARD_SCORE:
            return []
        if _creates_large_bounty_risk(state, player):
            return []
        if not _delivery_has_guard_slack(state, player, current):
            return []
        if not _opponent_will_need_node(state, player, current):
            return []

        extra_good_fruit = _extra_good_fruit_for_guard(state, player, current, candidate_score)
        if player.good_fruit <= _base_guard_cost(state, current) + extra_good_fruit + 18:
            return []

        self._attempted_nodes.add(current)
        return [set_guard(current, extra_good_fruit=extra_good_fruit)]


def _delivery_has_guard_slack(state: GameState, player: PlayerState, current: str) -> bool:
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
    if (
        current == "S10"
        and candidate_score >= 110
        and player.task_score >= 110
        and player.good_fruit >= 45
        and state.round_no < 360
    ):
        return 1
    return 0


def _base_guard_cost(state: GameState, current: str) -> int:
    if current == state.game_map.gate_node_id:
        return 1
    map_node = state.game_map.nodes.get(current)
    node_type = str(
        (map_node.raw if map_node else {}).get("nodeType")
        or (map_node.raw if map_node else {}).get("type")
        or ""
    ).upper()
    return 1 if node_type == "KEY_PASS" else 0


def _has_active_guard(node: Optional[NodeState]) -> bool:
    guard = (node.guard if node else None) or {}
    return bool(guard) and guard.get("active") is not False and int(guard.get("defense") or 0) > 0


def _active_own_guard_count(state: GameState, player: PlayerState) -> int:
    count = 0
    for node in state.nodes.values():
        guard = node.guard or {}
        owner_team_id = str(guard.get("ownerTeamId") or guard.get("teamId") or "")
        if owner_team_id == player.team_id and _has_active_guard(node):
            count += 1
    return count


def _creates_large_bounty_risk(state: GameState, player: PlayerState) -> bool:
    if player.total_score <= 0:
        return False
    for other in state.players.values():
        if other.player_id == player.player_id or other.team_id == player.team_id:
            continue
        if other.total_score > 0 and player.total_score - other.total_score >= 60:
            return True
    return False
