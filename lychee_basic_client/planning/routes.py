from lychee_basic_client.models.map import GameMap
from typing import Optional


def next_hop(game_map: GameMap, start_node_id: str, target_node_id: str) -> Optional[str]:
    path = game_map.shortest_path(start_node_id, target_node_id)
    if len(path) < 2:
        return None
    return path[1]
