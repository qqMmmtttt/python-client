from collections import deque
from dataclasses import dataclass, field
import heapq
from typing import Any, Optional


@dataclass(frozen=True)
class Node:
    node_id: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    route_type: str = ""
    distance: int = 0
    bidirectional: bool = True
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def travel_cost(self) -> int:
        return self.distance * ROUTE_COST.get(self.route_type, 1500)


@dataclass(frozen=True)
class ProcessNode:
    node_id: str
    process_type: str = ""
    process_round: int = 0
    can_window: bool = True
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameMap:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    start_node_id: str = "S01"
    gate_node_id: str = "S14"
    terminal_node_ids: list[str] = field(default_factory=lambda: ["S15"])
    process_nodes: dict[str, ProcessNode] = field(default_factory=dict)

    @classmethod
    def from_start(cls, data: dict[str, Any]) -> "GameMap":
        map_data = data.get("map") or {}
        gameplay = map_data.get("gameplay") or {}
        roles = gameplay.get("roles") or {}
        raw_nodes = data.get("nodes") or map_data.get("nodes") or []
        raw_edges = data.get("edges") or map_data.get("edges") or []
        return cls(
            nodes=_parse_nodes(raw_nodes),
            edges=_parse_edges(raw_edges),
            start_node_id=roles.get("startNodeId") or _find_node_by_type(raw_nodes, "START") or "S01",
            gate_node_id=roles.get("gateNodeId") or _find_node_by_type(raw_nodes, "GATE") or "S14",
            terminal_node_ids=list(
                roles.get("terminalNodeIds") or _find_nodes_by_type(raw_nodes, "FINISH") or ["S15"]
            ),
            process_nodes=_parse_process_nodes(data, map_data, gameplay, raw_nodes),
        )

    def with_runtime_edges(self, edges: list[dict[str, Any]]) -> "GameMap":
        if not edges:
            return self
        return GameMap(
            nodes=self.nodes,
            edges=_parse_edges(edges),
            start_node_id=self.start_node_id,
            gate_node_id=self.gate_node_id,
            terminal_node_ids=self.terminal_node_ids,
            process_nodes=self.process_nodes,
        )

    def neighbors(self, node_id: str) -> list[str]:
        neighbors: list[str] = []
        for edge in self.edges:
            if edge.from_node_id == node_id:
                neighbors.append(edge.to_node_id)
            if edge.bidirectional and edge.to_node_id == node_id:
                neighbors.append(edge.from_node_id)
        return sorted(set(neighbors))

    def shortest_path(self, start: str, target: str) -> list[str]:
        if start == target:
            return [start]
        queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
        visited = {start}
        while queue:
            node_id, path = queue.popleft()
            for neighbor in self.neighbors(node_id):
                if neighbor in visited:
                    continue
                next_path = path + [neighbor]
                if neighbor == target:
                    return next_path
                visited.add(neighbor)
                queue.append((neighbor, next_path))
        return []

    def fastest_path(self, start: str, target: str) -> list[str]:
        if start == target:
            return [start]

        queue: list[tuple[int, str, list[str]]] = [(0, start, [start])]
        best_cost: dict[str, int] = {start: 0}

        while queue:
            cost, node_id, path = heapq.heappop(queue)
            if node_id == target:
                return path
            if cost > best_cost.get(node_id, cost):
                continue
            for edge, neighbor in self.iter_neighbor_edges(node_id):
                next_cost = cost + edge.travel_cost
                if next_cost >= best_cost.get(neighbor, 1_000_000_000):
                    continue
                best_cost[neighbor] = next_cost
                heapq.heappush(queue, (next_cost, neighbor, path + [neighbor]))
        return []

    def iter_neighbor_edges(self, node_id: str) -> list[tuple[Edge, str]]:
        neighbors: list[tuple[Edge, str]] = []
        for edge in self.edges:
            if edge.from_node_id == node_id:
                neighbors.append((edge, edge.to_node_id))
            if edge.bidirectional and edge.to_node_id == node_id:
                neighbors.append((edge, edge.from_node_id))
        return neighbors

    def process_node(self, node_id: str) -> Optional[ProcessNode]:
        return self.process_nodes.get(node_id)


ROUTE_COST = {
    "ROAD": 1380,
    "WATER": 1250,
    "MOUNTAIN": 1780,
    "BRANCH": 1550,
}


def _parse_nodes(raw_nodes: list[dict[str, Any]]) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    for raw in raw_nodes:
        node_id = raw.get("nodeId")
        if node_id:
            nodes[node_id] = Node(node_id=node_id, raw=raw)
    return nodes


def _parse_edges(raw_edges: list[dict[str, Any]]) -> list[Edge]:
    edges: list[Edge] = []
    for index, raw in enumerate(raw_edges):
        from_node_id = _first_present(raw, "fromNodeId", "fromNode")
        to_node_id = _first_present(raw, "toNodeId", "toNode")
        if not from_node_id or not to_node_id:
            continue
        edges.append(
            Edge(
                edge_id=raw.get("edgeId") or f"edge-{index}",
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                route_type=raw.get("routeType") or "",
                distance=int(raw.get("distance") or 0),
                bidirectional=bool(raw.get("bidirectional", True)),
                raw=raw,
            )
        )
    return edges


def _parse_process_nodes(
    data: dict[str, Any],
    map_data: dict[str, Any],
    gameplay: dict[str, Any],
    raw_nodes: list[dict[str, Any]],
) -> dict[str, ProcessNode]:
    process_nodes: dict[str, ProcessNode] = {}

    for raw in gameplay.get("processNodes") or []:
        node_id = raw.get("nodeId")
        if not node_id:
            continue
        process_nodes[node_id] = ProcessNode(
            node_id=node_id,
            process_type=raw.get("processType") or "",
            process_round=int(raw.get("processRound") or 0),
            can_window=bool(raw.get("canWindow", True)),
            raw=raw,
        )

    for raw in data.get("processNodes") or []:
        _add_process_node(process_nodes, raw)

    for raw in map_data.get("processNodes") or []:
        _add_process_node(process_nodes, raw)

    for raw in raw_nodes:
        node_id = raw.get("nodeId")
        process_type = raw.get("processType")
        if node_id and process_type and node_id not in process_nodes:
            process_nodes[node_id] = ProcessNode(
                node_id=node_id,
                process_type=process_type,
                process_round=int(raw.get("processRound") or 0),
                can_window=bool(raw.get("canWindow", True)),
                raw=raw,
            )
    return process_nodes


def _add_process_node(process_nodes: dict[str, ProcessNode], raw: dict[str, Any]) -> None:
    node_id = raw.get("nodeId")
    if not node_id:
        return
    process_nodes[node_id] = ProcessNode(
        node_id=node_id,
        process_type=raw.get("processType") or _infer_process_type(raw),
        process_round=int(raw.get("processRound") or 0),
        can_window=bool(raw.get("canWindow", True)),
        raw=raw,
    )


def _infer_process_type(raw: dict[str, Any]) -> str:
    node_id = raw.get("nodeId")
    name = raw.get("processName") or ""
    if node_id == "S14" or "验核" in name:
        return "VERIFY"
    if "登船" in name:
        return "BOARD"
    if "水驿" in name:
        return "WATER_TRANSFER"
    if "宫前" in name:
        return "PALACE_TRANSFER"
    if "通行" in name or "关驿" in name:
        return "PASS_TRANSFER"
    return "TRANSFER"


def _find_node_by_type(raw_nodes: list[dict[str, Any]], node_type: str) -> Optional[str]:
    for raw in raw_nodes:
        if raw.get("type") == node_type or raw.get("nodeType") == node_type or raw.get(node_type.lower()):
            return raw.get("nodeId")
    return None


def _find_nodes_by_type(raw_nodes: list[dict[str, Any]], node_type: str) -> list[str]:
    return [
        raw["nodeId"]
        for raw in raw_nodes
        if raw.get("nodeId")
        and (raw.get("type") == node_type or raw.get("nodeType") == node_type or raw.get("terminal"))
    ]


def _first_present(raw: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return str(value)
    return None
