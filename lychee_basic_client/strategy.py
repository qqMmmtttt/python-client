from typing import Optional

from .config import Config
from .messages import heartbeat_action, move_action


class MovementStrategy:
    def __init__(self, config: Config) -> None:
        self._config = config
        self._current_node: Optional[str] = None
        self._edges: list[dict] = []
        self._match_id: str = ""

    def update_map(self, nodes: list[dict], edges: list[dict], match_id: str) -> None:
        self._edges = edges
        self._match_id = match_id

    def update_position(self, node_id: Optional[str]) -> None:
        self._current_node = node_id

    def get_legal_neighbors(self, node_id: str) -> list[str]:
        neighbors: list[str] = []
        for edge in self._edges:
            if edge.get("fromNodeId") == node_id or edge.get("fromNode") == node_id:
                neighbors.append(edge.get("toNodeId") or edge.get("toNode"))
            if edge.get("bidirectional", True):
                if edge.get("toNodeId") == node_id or edge.get("toNode") == node_id:
                    neighbors.append(edge.get("fromNodeId") or edge.get("fromNode"))
        return list(set(neighbors))

    def decide_action(
        self, round_no: int, player_id: int, current_node: Optional[str]
    ) -> dict:
        self._current_node = current_node

        if current_node is None:
            return heartbeat_action(self._match_id, round_no, player_id)

        neighbors = self.get_legal_neighbors(current_node)
        if not neighbors:
            return heartbeat_action(self._match_id, round_no, player_id)

        target = neighbors[0]
        return move_action(self._match_id, round_no, player_id, target)