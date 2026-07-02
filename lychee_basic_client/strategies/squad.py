from typing import Any

from lychee_basic_client.protocol.actions import squad_clear, squad_scout, squad_weaken
from lychee_basic_client.rules.blocking import enemy_guard_at
from lychee_basic_client.strategies.context import StrategyContext


SCOUT_TARGETS = ("S04", "S05", "S11", "S13", "S14")


class SquadStrategy:
    """Independent small-team actions that should not block the main convoy."""

    def __init__(self) -> None:
        self._dispatched_scout_targets: set[str] = set()
        self._dispatched_clear_targets: set[str] = set()
        self._dispatched_weaken_targets: set[str] = set()

    def on_start(self, state: Any) -> None:
        self._dispatched_scout_targets.clear()
        self._dispatched_clear_targets.clear()
        self._dispatched_weaken_targets.clear()
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None or player.delivered:
            return []
        if state.phase == "RUSH" or player.squad_available <= 0:
            return []

        weaken_target = _weaken_target_on_route(context, self._dispatched_weaken_targets)
        if weaken_target and player.squad_available >= 2:
            self._dispatched_weaken_targets.add(weaken_target)
            return [squad_weaken(weaken_target)]

        clear_target = _clear_target_on_route(context, self._dispatched_clear_targets)
        if clear_target and player.squad_available >= 2:
            self._dispatched_clear_targets.add(clear_target)
            return [squad_clear(clear_target)]

        for target in SCOUT_TARGETS:
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
            return [squad_scout(target)]
        return []


def _clear_target_on_route(
    context: StrategyContext,
    dispatched_clear_targets: set[str],
) -> str:
    state = context.state
    player = state.me
    if player is None or not player.current_node_id:
        return ""

    target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = state.game_map.fastest_path(player.current_node_id, target)
    for node_id in path[1:]:
        if node_id in dispatched_clear_targets:
            continue
        node = state.nodes.get(node_id)
        if node is not None and node.has_obstacle:
            return node_id
    return ""


def _weaken_target_on_route(
    context: StrategyContext,
    dispatched_targets: set[str],
) -> str:
    state = context.state
    player = state.me
    if player is None or not player.current_node_id:
        return ""

    target = state.game_map.terminal_node_ids[0] if player.verified else state.game_map.gate_node_id
    path = state.game_map.fastest_path(player.current_node_id, target)
    for node_id in path[1:]:
        if node_id in dispatched_targets:
            continue
        if enemy_guard_at(state.nodes.get(node_id), player) is not None:
            return node_id
    return ""


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
