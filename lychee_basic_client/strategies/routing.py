import heapq
from typing import Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.map import Edge, GameMap
from lychee_basic_client.models.state import GameState
from lychee_basic_client.planning.route_profiles import (
    FIRST_ROUND_EDGE_DISTANCES,
    FIRST_ROUND_SAFE_ROUTE,
)


class RoutePolicy:
    def __init__(self, config: Config) -> None:
        self._profile_name = config.route_profile

    def next_hop(self, state: GameState, current: str, target: str) -> Optional[str]:
        profile_hop = self._profile_next_hop(state.game_map, current, target)
        if profile_hop is not None:
            return profile_hop

        path = self._dynamic_path(state, current, target)
        if len(path) >= 2:
            return path[1]
        return None

    def _profile_next_hop(
        self, game_map: GameMap, current: str, target: str
    ) -> Optional[str]:
        if self._profile_name == "generic":
            return None
        if self._profile_name == "auto" and not _first_round_signature_matches(game_map):
            return None
        if not _route_profile_available(game_map, FIRST_ROUND_SAFE_ROUTE):
            return None
        if current not in FIRST_ROUND_SAFE_ROUTE or target not in FIRST_ROUND_SAFE_ROUTE:
            return None
        current_index = FIRST_ROUND_SAFE_ROUTE.index(current)
        target_index = FIRST_ROUND_SAFE_ROUTE.index(target)
        if current_index >= target_index:
            return None
        candidate = FIRST_ROUND_SAFE_ROUTE[current_index + 1]
        if candidate in game_map.neighbors(current):
            return candidate
        return None

    def _dynamic_path(self, state: GameState, start: str, target: str) -> list[str]:
        if start == target:
            return [start]

        queue: list[tuple[float, str, list[str]]] = [(0.0, start, [start])]
        best_cost: dict[str, float] = {start: 0.0}

        while queue:
            cost, node_id, path = heapq.heappop(queue)
            if node_id == target:
                return path
            if cost > best_cost.get(node_id, cost):
                continue

            for edge, neighbor in state.game_map.iter_neighbor_edges(node_id):
                next_cost = cost + _edge_cost(state, edge, neighbor)
                if next_cost >= best_cost.get(neighbor, float("inf")):
                    continue
                best_cost[neighbor] = next_cost
                heapq.heappush(queue, (next_cost, neighbor, path + [neighbor]))
        return []


def _route_profile_available(game_map: GameMap, route: list[str]) -> bool:
    if not all(node_id in game_map.nodes for node_id in route):
        return False
    for left, right in zip(route, route[1:]):
        if right not in game_map.neighbors(left):
            return False
    return True


def _first_round_signature_matches(game_map: GameMap) -> bool:
    if len(game_map.nodes) != 15 or len(game_map.edges) != 21:
        return False

    edge_distances = {
        (edge.from_node_id, edge.to_node_id): edge.distance for edge in game_map.edges
    }
    reverse_distances = {
        (edge.to_node_id, edge.from_node_id): edge.distance for edge in game_map.edges
    }
    for key, expected_distance in FIRST_ROUND_EDGE_DISTANCES.items():
        distance = edge_distances.get(key, reverse_distances.get(key))
        if distance != expected_distance:
            return False
    return True


def _edge_cost(state: GameState, edge: Edge, neighbor: str) -> float:
    cost = float(edge.travel_cost) * state.weather.route_multiplier(edge.route_type)
    node = state.nodes.get(neighbor)
    if node is not None and node.has_obstacle:
        cost += 250_000
    player = state.me
    guard = node.guard if node is not None else None
    if player is not None and guard:
        owner_team_id = guard.get("ownerTeamId")
        defense = int(guard.get("defense") or 0)
        if owner_team_id and owner_team_id != player.team_id and defense > 0:
            cost += 180_000 + defense * 30_000
    return cost
