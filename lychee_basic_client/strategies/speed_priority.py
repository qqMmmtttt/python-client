from typing import Any, Optional

from lychee_basic_client.models.state import GameState, PlayerState
from lychee_basic_client.planning.estimates import estimate_path_rounds
from lychee_basic_client.planning.route_profiles import FIRST_ROUND_WATER_ROUTE


SPEED_PRIORITY_PROFILE = "speed-priority"
WUGUAN_NODE_ID = "S10"
WUGUAN_RACE_BUFFER_ROUNDS = 8
WUGUAN_GUARD_MIN_OPPONENT_ETA = 12

WUGUAN_RACE_ROUTE = FIRST_ROUND_WATER_ROUTE[
    : FIRST_ROUND_WATER_ROUTE.index(WUGUAN_NODE_ID) + 1
]


def profile_is_speed_priority(profile_name: str) -> bool:
    return profile_name == SPEED_PRIORITY_PROFILE


def route_policy_is_speed_priority(route_policy: Any) -> bool:
    if route_policy is None:
        return False
    checker = getattr(route_policy, "is_speed_priority", None)
    if callable(checker):
        return bool(checker())
    return False


def has_own_active_guard(node: Any, player: PlayerState) -> bool:
    guard = getattr(node, "guard", None) or {}
    if guard.get("active") is False:
        return False
    owner = str(guard.get("ownerTeamId") or guard.get("teamId") or "")
    return bool(owner) and owner == player.team_id


def should_skip_task_for_wuguan_guard(
    route_policy: Any,
    state: GameState,
    current_node_id: str,
) -> bool:
    if not route_policy_is_speed_priority(route_policy):
        return False
    if current_node_id != WUGUAN_NODE_ID:
        return False
    player = state.me
    if player is None:
        return False
    node = state.nodes.get(current_node_id)
    if node is None:
        return False
    return not has_own_active_guard(node, player)


def should_prioritize_wuguan(
    route_policy: Any,
    state: GameState,
    current_node_id: Optional[str],
) -> bool:
    if not route_policy_is_speed_priority(route_policy):
        return False
    if not current_node_id:
        return False
    if not _water_race_route_available(state):
        return False
    current_index = _route_index(current_node_id)
    return 0 <= current_index < _route_index(WUGUAN_NODE_ID)


def speed_priority_task_target_allowed(
    route_policy: Any,
    state: GameState,
    current_node_id: str,
    task_target: Any,
) -> bool:
    if not should_prioritize_wuguan(route_policy, state, current_node_id):
        return True
    stand_node_id = str(getattr(task_target, "stand_node_id", "") or "")
    if not _is_forward_water_race_target(current_node_id, stand_node_id):
        return False
    if stand_node_id == WUGUAN_NODE_ID:
        return True
    process_round = int((getattr(task_target, "task", {}) or {}).get("processRound") or 5)
    return can_spend_before_wuguan(
        state,
        current_node_id,
        extra_rounds=process_round,
        buffer_rounds=_wuguan_race_buffer_rounds(process_round),
    )


def speed_priority_claim_current_task_allowed(
    route_policy: Any,
    state: GameState,
    current_node_id: str,
    task: dict[str, Any],
) -> bool:
    if not should_prioritize_wuguan(route_policy, state, current_node_id):
        return True
    if current_node_id == WUGUAN_NODE_ID:
        return True
    process_round = int(task.get("processRound") or 5)
    return can_spend_before_wuguan(
        state,
        current_node_id,
        extra_rounds=process_round,
        buffer_rounds=_wuguan_race_buffer_rounds(process_round),
    )


def _wuguan_race_buffer_rounds(process_round: int) -> int:
    """快任务（≤3 帧处理）降低缓冲，更容易接取；慢任务保持保守。"""
    if process_round <= 3:
        return 3
    if process_round <= 4:
        return 5
    return WUGUAN_RACE_BUFFER_ROUNDS


def can_spend_before_wuguan(
    state: GameState,
    current_node_id: str,
    *,
    extra_rounds: int,
    buffer_rounds: int,
) -> bool:
    player = state.me
    if player is None:
        return False
    my_eta = eta_to_wuguan_on_water_route(state, current_node_id)
    if my_eta is None:
        return False
    opponent_eta = opponent_eta_to_wuguan(state, player)
    if opponent_eta is None:
        return True
    return my_eta + extra_rounds + buffer_rounds < opponent_eta


def eta_to_wuguan_on_water_route(
    state: GameState,
    current_node_id: str,
) -> Optional[int]:
    if not _is_forward_water_race_target(current_node_id, WUGUAN_NODE_ID):
        return None
    current_index = _route_index(current_node_id)
    target_index = _route_index(WUGUAN_NODE_ID)
    path = WUGUAN_RACE_ROUTE[current_index : target_index + 1]
    return estimate_path_rounds(state, path, include_process=True)


def opponent_eta_to_wuguan(
    state: GameState,
    player: PlayerState,
) -> Optional[int]:
    best: Optional[int] = None
    for other in state.players.values():
        if other.player_id == player.player_id or other.team_id == player.team_id:
            continue
        other_node = other.current_node_id
        if not other_node:
            continue
        target = state.game_map.terminal_node_ids[0] if other.verified else state.game_map.gate_node_id
        future_path = state.game_map.fastest_path(other_node, target)
        if WUGUAN_NODE_ID not in future_path:
            continue
        path_to_wuguan = future_path[: future_path.index(WUGUAN_NODE_ID) + 1]
        eta = estimate_path_rounds(state, path_to_wuguan, include_process=True)
        if best is None or eta < best:
            best = eta
    return best


def wuguan_guard_extra_good_fruit(state: GameState, player: PlayerState) -> int:
    opponent_eta = opponent_eta_to_wuguan(state, player)
    if opponent_eta is not None and opponent_eta >= 24 and player.good_fruit >= 60:
        return 1
    return 0


def _water_race_route_available(state: GameState) -> bool:
    for left, right in zip(WUGUAN_RACE_ROUTE, WUGUAN_RACE_ROUTE[1:]):
        if right not in state.game_map.neighbors(left):
            return False
    return True


def _is_forward_water_race_target(current_node_id: str, target_node_id: str) -> bool:
    current_index = _route_index(current_node_id)
    target_index = _route_index(target_node_id)
    wuguan_index = _route_index(WUGUAN_NODE_ID)
    if current_index < 0 or target_index < 0:
        return False
    return current_index <= target_index <= wuguan_index


def _route_index(node_id: Optional[str]) -> int:
    if not node_id:
        return -1
    try:
        return WUGUAN_RACE_ROUTE.index(node_id)
    except ValueError:
        return -1
