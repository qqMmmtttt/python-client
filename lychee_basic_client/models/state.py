from dataclasses import dataclass, field
from typing import Any, Optional

from .map import GameMap


@dataclass(frozen=True)
class NodeState:
    node_id: str
    has_obstacle: bool = False
    resource_stock: dict[str, int] = field(default_factory=dict)
    guard: Optional[dict[str, Any]] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "NodeState":
        return cls(
            node_id=raw.get("nodeId") or "",
            has_obstacle=bool(raw.get("hasObstacle", False)),
            resource_stock=dict(raw.get("resourceStock") or {}),
            guard=raw.get("guard"),
            raw=raw,
        )


@dataclass(frozen=True)
class PlayerState:
    player_id: int
    team_id: str = ""
    state: str = ""
    current_node_id: Optional[str] = None
    next_node_id: Optional[str] = None
    verified: bool = False
    delivered: bool = False
    freshness: float = 0.0
    good_fruit: int = 0
    bad_fruit: int = 0
    guard_action_point: int = 0
    task_score: int = 0
    total_score: int = 0
    resources: dict[str, int] = field(default_factory=dict)
    current_process: Optional[dict[str, Any]] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "PlayerState":
        return cls(
            player_id=int(raw.get("playerId") or 0),
            team_id=raw.get("teamId") or "",
            state=raw.get("state") or "",
            current_node_id=raw.get("currentNodeId"),
            next_node_id=raw.get("nextNodeId"),
            verified=bool(raw.get("verified", False)),
            delivered=bool(raw.get("delivered", False)),
            freshness=float(raw.get("freshness") or 0),
            good_fruit=int(raw.get("goodFruit") or 0),
            bad_fruit=int(raw.get("badFruit") or 0),
            guard_action_point=int(raw.get("guardActionPoint") or 0),
            task_score=int(raw.get("taskScore") or 0),
            total_score=int(raw.get("totalScore") or 0),
            resources=dict(raw.get("resources") or {}),
            current_process=raw.get("currentProcess"),
            raw=raw,
        )


@dataclass
class GameState:
    match_id: str
    round_no: int
    player_id: int
    phase: str = "NORMAL"
    game_map: GameMap = field(default_factory=GameMap)
    players: dict[int, PlayerState] = field(default_factory=dict)
    nodes: dict[str, NodeState] = field(default_factory=dict)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    contests: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    action_results: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def me(self) -> Optional[PlayerState]:
        return self.players.get(self.player_id)

    @classmethod
    def from_start(cls, data: dict[str, Any], player_id: int) -> "GameState":
        game_map = GameMap.from_start(data)
        return cls(
            match_id=data["matchId"],
            round_no=int(data.get("round") or 1),
            player_id=player_id,
            phase=data.get("phase") or "NORMAL",
            game_map=game_map,
            players=_parse_players(data.get("players") or []),
            nodes=_parse_nodes(data.get("nodes") or []),
            resources=list(data.get("resources") or []),
            raw=data,
        )

    @classmethod
    def from_inquire(
        cls, data: dict[str, Any], player_id: int, previous_map: GameMap
    ) -> "GameState":
        return cls(
            match_id=data["matchId"],
            round_no=int(data["round"]),
            player_id=player_id,
            phase=data.get("phase") or "NORMAL",
            game_map=previous_map.with_runtime_edges(data.get("edges") or []),
            players=_parse_players(data.get("players") or []),
            nodes=_parse_nodes(data.get("nodes") or []),
            tasks=list(data.get("tasks") or []),
            contests=list(data.get("contests") or []),
            events=list(data.get("events") or []),
            action_results=list(data.get("actionResults") or []),
            raw=data,
        )


def _parse_players(raw_players: list[dict[str, Any]]) -> dict[int, PlayerState]:
    players: dict[int, PlayerState] = {}
    for raw in raw_players:
        player = PlayerState.from_raw(raw)
        if player.player_id:
            players[player.player_id] = player
    return players


def _parse_nodes(raw_nodes: list[dict[str, Any]]) -> dict[str, NodeState]:
    nodes: dict[str, NodeState] = {}
    for raw in raw_nodes:
        node = NodeState.from_raw(raw)
        if node.node_id:
            nodes[node.node_id] = node
    return nodes
