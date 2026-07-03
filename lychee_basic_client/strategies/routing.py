import heapq
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.map import Edge, GameMap
from lychee_basic_client.models.state import GameState
from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.planning.route_profiles import (
    ALTERNATE_ROUTE_AFTER_S02_LOSS,
    FIRST_ROUND_WATER_ROUTE,
)
from lychee_basic_client.rules.blocking import enemy_guard_at, obstacle_residue_tax_round
from lychee_basic_client.strategies.speed_priority import SPEED_PRIORITY_PROFILE


S02_NODE_ID = "S02"


class RoutePolicy:
    def __init__(self, config: Config) -> None:
        self._profile_name = config.route_profile
        self._alternate_route_active = False
        self._handled_contest_ids: set[str] = set()
        self._logger = get_logger("strategies.routing")

    def on_start(self, state: GameState) -> None:
        self._alternate_route_active = False
        self._handled_contest_ids.clear()
        return None

    def observe_contest_result(self, state: GameState) -> None:
        """检测窗口争夺结果；南岭驿（S02）争夺失败后切换到替代路线。"""
        if self._alternate_route_active:
            return
        player = state.me
        if player is None:
            return
        for contest in state.contests:
            if not contest.get("resolved"):
                continue
            contest_id = str(contest.get("contestId") or "")
            if not contest_id or contest_id in self._handled_contest_ids:
                continue
            self._handled_contest_ids.add(contest_id)
            if str(contest.get("targetNodeId") or "") != S02_NODE_ID:
                continue
            if not _contest_involves_player(contest, state.player_id):
                continue
            winner = str(contest.get("winnerTeamId") or "")
            if winner and winner != player.team_id:
                self._alternate_route_active = True
                self._logger.important(
                    "alternate_route_activated round=%s contest=%s node=%s winner=%s team=%s"
                    " | 南岭驿窗口争夺失败：切换到替代路线 S02→S04→S07→S09→S10，放弃水路主段与武关竞速",
                    state.round_no,
                    contest_id,
                    S02_NODE_ID,
                    winner,
                    player.team_id,
                )
                break

    def next_hop(self, state: GameState, current: str, target: str) -> Optional[str]:
        path = self.path(state, current, target)
        if len(path) >= 2:
            return path[1]
        return None

    def path(self, state: GameState, current: str, target: str) -> list[str]:
        profile_path = self._profile_path(state.game_map, current, target)
        if profile_path:
            return profile_path
        return self._dynamic_path(state, current, target)

    def profile_next_hop(
        self, state: GameState, current: str, target: str
    ) -> Optional[str]:
        return self._profile_next_hop(state.game_map, current, target)

    def is_speed_priority(self) -> bool:
        if self._alternate_route_active:
            return False
        return self._profile_name == SPEED_PRIORITY_PROFILE

    def is_alternate_route_active(self) -> bool:
        return self._alternate_route_active

    def _profile_next_hop(
        self, game_map: GameMap, current: str, target: str
    ) -> Optional[str]:
        path = self._profile_path(game_map, current, target)
        if len(path) >= 2:
            return path[1]
        return None

    def _profile_path(
        self, game_map: GameMap, current: str, target: str
    ) -> list[str]:
        if self._profile_name == "generic":
            return []
        if self._profile_name == "auto":
            return []
        if self._alternate_route_active:
            return _profile_path(
                game_map, ALTERNATE_ROUTE_AFTER_S02_LOSS, current, target
            )
        if self._profile_name in {"first-round-safe", "first-round-water", SPEED_PRIORITY_PROFILE}:
            return _profile_path(game_map, FIRST_ROUND_WATER_ROUTE, current, target)
        return []

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


def _profile_path(
    game_map: GameMap, route: list[str], current: str, target: str
) -> list[str]:
    if not _route_profile_available(game_map, route):
        return []
    if current not in route or target not in route:
        return []
    current_index = route.index(current)
    target_index = route.index(target)
    if current_index >= target_index:
        return []
    return route[current_index : target_index + 1]


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


def _contest_involves_player(contest: dict[str, Any], player_id: int) -> bool:
    player_fields = [
        "redPlayerId",
        "bluePlayerId",
        "initiatorPlayerId",
    ]
    return any(contest.get(field) == player_id for field in player_fields)
