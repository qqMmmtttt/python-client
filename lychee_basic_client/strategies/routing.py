import heapq
from typing import Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.map import Edge, GameMap
from lychee_basic_client.models.state import GameState
from lychee_basic_client.planning.route_profiles import (
    FIRST_ROUND_WATER_EDGE_DISTANCES,
    FIRST_ROUND_WATER_ROUTE,
)
from lychee_basic_client.rules.blocking import enemy_guard_at, obstacle_residue_tax_round


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

    def profile_next_hop(
        self, state: GameState, current: str, target: str
    ) -> Optional[str]:
        return self._profile_next_hop(state.game_map, current, target)

    def _profile_next_hop(
        self, game_map: GameMap, current: str, target: str
    ) -> Optional[str]:
        if self._profile_name == "generic":
            return None
        if self._profile_name == "auto":
            if not _route_signature_matches(
                game_map,
                FIRST_ROUND_WATER_EDGE_DISTANCES,
            ):
                return None
            return _profile_hop(game_map, FIRST_ROUND_WATER_ROUTE, current, target)
        if self._profile_name in {"first-round-safe", "first-round-water"}:
            return _profile_hop(game_map, FIRST_ROUND_WATER_ROUTE, current, target)
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


def _profile_hop(
    game_map: GameMap, route: list[str], current: str, target: str
) -> Optional[str]:
    if not _route_profile_available(game_map, route):
        return None
    if current not in route or target not in route:
        return None
    current_index = route.index(current)
    target_index = route.index(target)
    if current_index >= target_index:
        return None
    candidate = route[current_index + 1]
    if candidate in game_map.neighbors(current):
        return candidate
    return None


def _route_signature_matches(game_map: GameMap, distances: dict[tuple[str, str], int]) -> bool:
    for (left, right), distance in distances.items():
        edge = _edge_between(game_map, left, right)
        if edge is None or edge.distance != distance:
            return False
    return True


def _edge_between(game_map: GameMap, left: str, right: str) -> Optional[Edge]:
    for edge, neighbor in game_map.iter_neighbor_edges(left):
        if neighbor == right:
            return edge
    return None


def _route_profile_available(game_map: GameMap, route: list[str]) -> bool:
    if not all(node_id in game_map.nodes for node_id in route):
        return False
    for left, right in zip(route, route[1:]):
        if right not in game_map.neighbors(left):
            return False
    return True


def _edge_cost(state: GameState, edge: Edge, neighbor: str) -> float:
    cost = float(edge.travel_cost) * state.weather.route_multiplier(edge.route_type)
    process_node = state.game_map.process_node(neighbor)
    if process_node is not None and process_node.process_type != "VERIFY":
        process_round = process_node.process_round
        if state.weather.has_active("HEAVY_RAIN") and process_node.process_type in {
            "BOARD",
            "WATER_TRANSFER",
        }:
            process_round += 4
        cost += float(process_round * 1000)
    node = state.nodes.get(neighbor)
    if node is not None and node.has_obstacle:
        cost += 250_000
    cost += obstacle_residue_tax_round(node, state.me) * 1000
    guard = enemy_guard_at(node, state.me)
    if guard is not None:
        cost += 180_000 + guard.defense * 30_000
    return cost
