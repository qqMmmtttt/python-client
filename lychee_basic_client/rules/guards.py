import math
from typing import Any

from lychee_basic_client.models.state import GameState, NodeState, PlayerState


GUARD_PROCESS_ROUNDS = 4
MAX_ACTIVE_OWN_GUARDS = 2
MAX_EXTRA_GUARD_GOOD_FRUIT = 2


def guard_base_good_fruit_cost(state: GameState, node_id: str) -> int:
    if node_id == state.game_map.gate_node_id:
        return 1
    node_type = guard_node_type(state, node_id)
    return 1 if node_type == "KEY_PASS" else 0


def guard_max_defense(state: GameState, node_id: str) -> int:
    if node_id in state.game_map.terminal_node_ids:
        return 0
    if node_id == state.game_map.gate_node_id:
        return 4
    node = state.nodes.get(node_id)
    if node is not None and node.has_obstacle:
        return 5
    node_type = guard_node_type(state, node_id)
    if node_type == "KEY_PASS":
        return 7
    return 6


def max_effective_extra_good_fruit(state: GameState, node_id: str) -> int:
    max_defense = guard_max_defense(state, node_id)
    if max_defense <= 2:
        return 0
    return min(MAX_EXTRA_GUARD_GOOD_FRUIT, math.ceil((max_defense - 2) / 2))


def guard_defense_after_extra(state: GameState, node_id: str, extra_good_fruit: int) -> int:
    return min(guard_max_defense(state, node_id), 2 + max(0, extra_good_fruit) * 2)


def can_pay_guard(
    state: GameState,
    player: PlayerState,
    node_id: str,
    extra_good_fruit: int,
    *,
    reserve_good_fruit: int,
) -> bool:
    cost = guard_base_good_fruit_cost(state, node_id) + extra_good_fruit
    return player.good_fruit > cost + reserve_good_fruit


def has_active_guard(node: NodeState | None) -> bool:
    guard = (node.guard if node else None) or {}
    return bool(guard) and guard.get("active") is not False and int(guard.get("defense") or 0) > 0


def has_own_active_guard(node: NodeState | None, player: PlayerState) -> bool:
    if not has_active_guard(node):
        return False
    guard = (node.guard if node else None) or {}
    owner_team_id = str(guard.get("ownerTeamId") or guard.get("teamId") or "")
    return owner_team_id == player.team_id


def active_own_guard_count(state: GameState, player: PlayerState) -> int:
    count = 0
    for node in state.nodes.values():
        if has_own_active_guard(node, player):
            count += 1
    return count


def guard_node_type(state: GameState, node_id: str) -> str:
    map_node = state.game_map.nodes.get(node_id)
    raw: dict[str, Any] = map_node.raw if map_node else {}
    return str(raw.get("nodeType") or raw.get("type") or "").upper()
