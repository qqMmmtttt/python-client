from dataclasses import dataclass, field
from typing import Any, Optional

from lychee_basic_client.models.map import Edge, GameMap
from lychee_basic_client.models.state import GameState, NodeState, PlayerState


@dataclass(frozen=True)
class PublicPlayerSnapshot:
    """每轮公开玩家信息，供策略层读取对手和己方状态。"""

    role: str
    player_id: int
    team_id: str
    state: str
    current_node_id: str
    next_node_id: str
    route_edge_id: str
    route_type: str
    move_direction: str
    edge_progress_ms: Optional[int]
    edge_total_ms: Optional[int]
    verified: bool
    delivered: bool
    freshness: float
    good_fruit: int
    bad_fruit: int
    guard_action_point: int
    rush_tactic_used_count: int
    break_order_ready: bool
    squad_available: int
    squad_in_flight: int
    task_score: int
    total_score: int
    resources: dict[str, int] = field(default_factory=dict)
    buffs: list[str] = field(default_factory=list)
    current_process: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicNodeSnapshot:
    """每轮公开节点信息，重点保留资源、障碍、设卡和探路标记。"""

    node_id: str
    name: str
    node_type: str
    has_obstacle: bool
    obstacle_type: str
    obstacle_owner: str
    obstacle_residue_round: Optional[int]
    resource_stock: dict[str, int] = field(default_factory=dict)
    guard: dict[str, Any] = field(default_factory=dict)
    scouts: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PublicTaskSnapshot:
    """每轮公开任务信息，保留皇榜任务的目标、归属、保护和过期状态。"""

    task_id: str
    task_template_id: str
    node_id: str
    score: int
    process_round: int
    owner_player_id: Optional[int]
    protection_player_id: Optional[int]
    expire_round: Optional[int]
    active: bool
    completed: bool
    failed: bool
    status: str


@dataclass(frozen=True)
class PublicWeatherSnapshot:
    """每轮公开天气信息，保留当前天气和预报天气。"""

    active: list[dict[str, Any]] = field(default_factory=list)
    forecast: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PublicContestSnapshot:
    """每轮公开窗口争夺信息。"""

    contest_id: str
    target_node_id: str
    status: str
    resolved: bool
    winner_team_id: str
    participants: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicEventSnapshot:
    """每轮公开事件信息，供策略判断动作是否真的结算生效。"""

    event_type: str
    player_id: Optional[int]
    node_id: str
    target_node_id: str
    task_id: str
    action: str
    score_delta: Optional[int]
    error_code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublicActionResultSnapshot:
    """每轮公开的上一帧动作结算结果。"""

    player_id: Optional[int]
    action: str
    accepted: Optional[bool]
    result: str
    error_code: str
    target_node_id: str
    resource_type: str
    task_id: str


@dataclass(frozen=True)
class PublicRoundSnapshot:
    """服务器每轮全量状态的结构化快照。"""

    match_id: str
    round_no: int
    phase: str
    self_player_id: int
    players: list[PublicPlayerSnapshot] = field(default_factory=list)
    nodes: list[PublicNodeSnapshot] = field(default_factory=list)
    tasks: list[PublicTaskSnapshot] = field(default_factory=list)
    weather: PublicWeatherSnapshot = field(default_factory=PublicWeatherSnapshot)
    contests: list[PublicContestSnapshot] = field(default_factory=list)
    events: list[PublicEventSnapshot] = field(default_factory=list)
    action_results: list[PublicActionResultSnapshot] = field(default_factory=list)

    @classmethod
    def from_state(cls, state: GameState) -> "PublicRoundSnapshot":
        return cls(
            match_id=state.match_id,
            round_no=state.round_no,
            phase=state.phase,
            self_player_id=state.player_id,
            players=_player_snapshots(state),
            nodes=_node_snapshots(state),
            tasks=_task_snapshots(state),
            weather=_weather_snapshot(state),
            contests=_contest_snapshots(state),
            events=_event_snapshots(state),
            action_results=_action_result_snapshots(state),
        )

    def player(self, player_id: int) -> Optional[PublicPlayerSnapshot]:
        for player in self.players:
            if player.player_id == player_id:
                return player
        return None

    def opponents(self) -> list[PublicPlayerSnapshot]:
        return [player for player in self.players if player.role == "对手"]

    def active_tasks(self) -> list[PublicTaskSnapshot]:
        return [task for task in self.tasks if task.active and not task.completed and not task.failed]


def _player_snapshots(state: GameState) -> list[PublicPlayerSnapshot]:
    players = sorted(state.players.values(), key=lambda item: item.player_id)
    return [_player_snapshot(state, player) for player in players]


def _player_snapshot(state: GameState, player: PlayerState) -> PublicPlayerSnapshot:
    raw = player.raw
    edge = _edge_for_player(state.game_map, player)
    return PublicPlayerSnapshot(
        role=_player_role(state, player),
        player_id=player.player_id,
        team_id=player.team_id,
        state=player.state,
        current_node_id=player.current_node_id or "",
        next_node_id=player.next_node_id or "",
        route_edge_id=str(raw.get("routeEdgeId") or ""),
        route_type=edge.route_type if edge else "",
        move_direction=str(raw.get("moveDirection") or ""),
        edge_progress_ms=_optional_int(raw.get("edgeProgressMs")),
        edge_total_ms=_optional_int(raw.get("edgeTotalMs")),
        verified=player.verified,
        delivered=player.delivered,
        freshness=player.freshness,
        good_fruit=player.good_fruit,
        bad_fruit=player.bad_fruit,
        guard_action_point=player.guard_action_point,
        rush_tactic_used_count=player.rush_tactic_used_count,
        break_order_ready=player.break_order_ready,
        squad_available=player.squad_available,
        squad_in_flight=_squad_in_flight(raw),
        task_score=player.task_score,
        total_score=player.total_score,
        resources=dict(player.resources),
        buffs=_buffs(raw),
        current_process=dict(player.current_process or {}),
    )


def _player_role(state: GameState, player: PlayerState) -> str:
    if player.player_id == state.player_id:
        return "我方"
    me = state.me
    if me is not None and player.team_id == me.team_id:
        return "同队"
    return "对手"


def _edge_for_player(game_map: GameMap, player: PlayerState) -> Optional[Edge]:
    if not player.current_node_id or not player.next_node_id:
        return None
    for edge in game_map.edges:
        if edge.from_node_id == player.current_node_id and edge.to_node_id == player.next_node_id:
            return edge
        if (
            edge.bidirectional
            and edge.to_node_id == player.current_node_id
            and edge.from_node_id == player.next_node_id
        ):
            return edge
    return None


def _squad_in_flight(raw: dict[str, Any]) -> int:
    value = raw.get("squadInFlight")
    if value is None:
        value = raw.get("squadBusy")
    if value is None:
        teams = raw.get("squads") or raw.get("squadTasks") or []
        if isinstance(teams, list):
            return len(teams)
    return int(value or 0)


def _buffs(raw: dict[str, Any]) -> list[str]:
    raw_buffs = raw.get("buffs") or raw.get("activeBuffs") or []
    if isinstance(raw_buffs, dict):
        return [str(key) for key, value in raw_buffs.items() if value]
    if isinstance(raw_buffs, list):
        return [str(item.get("type") if isinstance(item, dict) else item) for item in raw_buffs]
    return []


def _node_snapshots(state: GameState) -> list[PublicNodeSnapshot]:
    nodes = sorted(state.nodes.values(), key=lambda item: item.node_id)
    return [_node_snapshot(state.game_map, node) for node in nodes]


def _node_snapshot(game_map: GameMap, node: NodeState) -> PublicNodeSnapshot:
    raw = node.raw
    map_node = game_map.nodes.get(node.node_id)
    map_raw = map_node.raw if map_node else {}
    return PublicNodeSnapshot(
        node_id=node.node_id,
        name=str(
            raw.get("name")
            or raw.get("nodeName")
            or map_raw.get("name")
            or map_raw.get("nodeName")
            or ""
        ),
        node_type=str(
            raw.get("nodeType")
            or raw.get("type")
            or map_raw.get("nodeType")
            or map_raw.get("type")
            or ""
        ),
        has_obstacle=node.has_obstacle,
        obstacle_type=str(raw.get("obstacleType") or ""),
        obstacle_owner=str(raw.get("obstacleOwnerTeamId") or raw.get("obstacleOwner") or ""),
        obstacle_residue_round=_optional_int(
            raw.get("obstacleResidueRound") or raw.get("obstacleResidue")
        ),
        resource_stock=dict(node.resource_stock),
        guard=dict(node.guard or {}),
        scouts=list(raw.get("scouted") or raw.get("scouts") or []),
    )


def _task_snapshots(state: GameState) -> list[PublicTaskSnapshot]:
    tasks = [_task_snapshot(task) for task in state.tasks]
    return sorted(tasks, key=lambda item: (item.expire_round or 10**9, item.task_id))


def _task_snapshot(task: dict[str, Any]) -> PublicTaskSnapshot:
    active = bool(task.get("active", True))
    completed = bool(task.get("completed", False))
    failed = bool(task.get("failed", False))
    return PublicTaskSnapshot(
        task_id=str(task.get("taskId") or ""),
        task_template_id=str(task.get("taskTemplateId") or ""),
        node_id=str(task.get("nodeId") or task.get("targetNodeId") or ""),
        score=int(task.get("score") or 0),
        process_round=int(task.get("processRound") or 0),
        owner_player_id=_optional_int(task.get("ownerPlayerId")),
        protection_player_id=_optional_int(task.get("protectionPlayerId")),
        expire_round=_optional_int(task.get("expireRound")),
        active=active,
        completed=completed,
        failed=failed,
        status=_task_status(active, completed, failed),
    )


def _task_status(active: bool, completed: bool, failed: bool) -> str:
    if completed:
        return "已完成"
    if failed:
        return "已失败"
    if not active:
        return "未激活"
    return "可执行"


def _weather_snapshot(state: GameState) -> PublicWeatherSnapshot:
    raw = state.weather.raw
    return PublicWeatherSnapshot(
        active=list(raw.get("active") or raw.get("current") or []),
        forecast=list(raw.get("forecast") or raw.get("upcoming") or []),
    )


def _contest_snapshots(state: GameState) -> list[PublicContestSnapshot]:
    return [_contest_snapshot(contest) for contest in state.contests]


def _contest_snapshot(contest: dict[str, Any]) -> PublicContestSnapshot:
    return PublicContestSnapshot(
        contest_id=str(contest.get("contestId") or ""),
        target_node_id=str(contest.get("targetNodeId") or contest.get("nodeId") or ""),
        status=str(contest.get("status") or ""),
        resolved=bool(contest.get("resolved", False)),
        winner_team_id=str(contest.get("winnerTeamId") or ""),
        participants={
            key: contest.get(key)
            for key in ("redPlayerId", "bluePlayerId", "initiatorPlayerId")
            if key in contest
        },
    )


def _event_snapshots(state: GameState) -> list[PublicEventSnapshot]:
    return [_event_snapshot(event) for event in state.events]


def _event_snapshot(event: dict[str, Any]) -> PublicEventSnapshot:
    payload = dict(event.get("payload") or {})
    known_keys = {
        "playerId",
        "nodeId",
        "targetNodeId",
        "taskId",
        "action",
        "score",
        "scoreDelta",
        "errorCode",
        "message",
    }
    details = {key: value for key, value in payload.items() if key not in known_keys}
    return PublicEventSnapshot(
        event_type=str(event.get("type") or ""),
        player_id=_optional_int(payload.get("playerId")),
        node_id=str(payload.get("nodeId") or ""),
        target_node_id=str(payload.get("targetNodeId") or ""),
        task_id=str(payload.get("taskId") or ""),
        action=str(payload.get("action") or ""),
        score_delta=_optional_int(payload.get("score") or payload.get("scoreDelta")),
        error_code=str(payload.get("errorCode") or ""),
        message=str(payload.get("message") or ""),
        details=details,
    )


def _action_result_snapshots(state: GameState) -> list[PublicActionResultSnapshot]:
    return [_action_result_snapshot(result) for result in state.action_results]


def _action_result_snapshot(result: dict[str, Any]) -> PublicActionResultSnapshot:
    return PublicActionResultSnapshot(
        player_id=_optional_int(result.get("playerId")),
        action=str(result.get("action") or ""),
        accepted=_optional_bool(result.get("accepted")),
        result=str(result.get("result") or ""),
        error_code=str(result.get("errorCode") or ""),
        target_node_id=str(result.get("targetNodeId") or ""),
        resource_type=str(result.get("resourceType") or ""),
        task_id=str(result.get("taskId") or ""),
    )


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)
