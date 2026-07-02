import math
from typing import Optional

from lychee_basic_client.models.map import Edge
from lychee_basic_client.models.state import GameState


def estimate_edge_rounds(state: GameState, edge: Edge) -> int:
    multiplier = state.weather.route_multiplier(edge.route_type)
    return max(1, math.ceil(edge.travel_cost * multiplier / 1000))


def estimate_path_rounds(state: GameState, path: list[str], include_process: bool = True) -> int:
    if len(path) < 2:
        return 0

    total = 0
    for left, right in zip(path, path[1:]):
        edge = _edge_between(state, left, right)
        if edge is None:
            return 1_000_000
        total += estimate_edge_rounds(state, edge)
        if include_process and right != state.game_map.gate_node_id:
            process_node = state.game_map.process_node(right)
            if process_node is not None and process_node.process_type != "VERIFY":
                total += max(0, process_node.process_round)
    return total


def estimate_delivery_rounds(state: GameState, start_node_id: str, verified: bool = False) -> int:
    gate = state.game_map.gate_node_id
    terminal = state.game_map.terminal_node_ids[0]

    total = 0
    if not verified and start_node_id != gate:
        path_to_gate = state.game_map.fastest_path(start_node_id, gate)
        total += estimate_path_rounds(state, path_to_gate)
    if not verified:
        total += 6

    if start_node_id == terminal and verified:
        return 0
    path_from_gate = state.game_map.fastest_path(gate if not verified else start_node_id, terminal)
    total += estimate_path_rounds(state, path_from_gate, include_process=False)
    total += 1
    return total


def _edge_between(state: GameState, left: str, right: str) -> Optional[Edge]:
    for edge, neighbor in state.game_map.iter_neighbor_edges(left):
        if neighbor == right:
            return edge
    return None
