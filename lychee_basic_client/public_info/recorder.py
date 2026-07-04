from pathlib import Path
from typing import Any, Iterable

from .snapshot import (
    PublicActionResultSnapshot,
    PublicContestSnapshot,
    PublicEventSnapshot,
    PublicNodeSnapshot,
    PublicPlayerSnapshot,
    PublicRoundSnapshot,
    PublicTaskSnapshot,
)


class PublicStateRecorder:
    """把每轮公开状态写成中文档案，便于人工复盘和后续策略扩展。"""

    def __init__(self, log_dir: str, dirname: str = "public_state") -> None:
        self._directory = Path(log_dir) / dirname

    @property
    def directory(self) -> Path:
        return self._directory

    def record(self, snapshot: PublicRoundSnapshot, *, source: str = "inquire") -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        suffix = "_start" if source == "start" else ""
        path = self._directory / f"round_{snapshot.round_no:04d}{suffix}.txt"
        path.write_text(render_public_round_snapshot(snapshot), encoding="utf-8")
        return path


def render_public_round_snapshot(snapshot: PublicRoundSnapshot) -> str:
    lines: list[str] = [
        f"第 {snapshot.round_no:04d} 轮公开状态档案",
        "",
        "一、基础信息",
        f"- matchId（比赛编号）：{_text(snapshot.match_id)}",
        f"- round（结算轮次）：{snapshot.round_no}",
        f"- phase（比赛阶段）：{_phase_name(snapshot.phase)}",
        f"- selfPlayerId（我方玩家编号）：{snapshot.self_player_id}",
        "",
        "二、玩家信息（服务器每轮公开所有玩家状态，策略可用来判断对手位置、资源和是否已交付）",
    ]
    if snapshot.players:
        for player in snapshot.players:
            lines.extend(_render_player(player))
    else:
        lines.append("- 本轮没有玩家状态。")

    lines.extend(["", "三、节点信息（只记录本轮服务器公开的运行时节点状态）"])
    if snapshot.nodes:
        for node in snapshot.nodes:
            lines.extend(_render_node(node))
    else:
        lines.append("- 本轮没有公开节点状态。")

    lines.extend(["", "四、任务信息（皇榜任务状态，用于决定抢任务、放弃任务或赶路）"])
    if snapshot.tasks:
        for task in snapshot.tasks:
            lines.extend(_render_task(task))
    else:
        lines.append("- 本轮没有公开任务。")

    lines.extend(["", "五、天气信息（影响路线速度、处理时间和鲜度损耗）"])
    lines.extend(_render_weather_group("active（当前生效天气）", snapshot.weather.active))
    lines.extend(_render_weather_group("forecast（后续预报天气）", snapshot.weather.forecast))

    lines.extend(["", "六、窗口争夺信息（用于判断争夺结果和路线切换）"])
    if snapshot.contests:
        for contest in snapshot.contests:
            lines.extend(_render_contest(contest))
    else:
        lines.append("- 本轮没有窗口争夺信息。")

    lines.extend(["", "七、事件信息（动作是否真正结算生效，优先看这里）"])
    if snapshot.events:
        for event in snapshot.events:
            lines.extend(_render_event(event))
    else:
        lines.append("- 本轮没有事件。")

    lines.extend(["", "八、上一帧动作结果（服务器对上一轮动作的接收和拒绝原因）"])
    if snapshot.action_results:
        for result in snapshot.action_results:
            lines.extend(_render_action_result(result))
    else:
        lines.append("- 本轮没有动作结果。")

    lines.append("")
    return "\n".join(lines)


def _render_player(player: PublicPlayerSnapshot) -> list[str]:
    return [
        f"- 玩家 {player.player_id}（{player.role}）：",
        f"  - playerId（玩家编号）：{player.player_id}",
        f"  - teamId（队伍编号）：{_text(player.team_id)}",
        f"  - state（主车队状态）：{_state_name(player.state)}",
        f"  - currentNodeId（停靠时为所在节点；移动中为路线起点）：{_text(player.current_node_id)}",
        f"  - nextNodeId（移动中为目标节点；空表示当前不在路线边）：{_text(player.next_node_id)}",
        f"  - routeEdgeId（当前路线边编号）：{_text(player.route_edge_id)}",
        f"  - routeType（当前路线类型）：{_route_type_name(player.route_type)}",
        f"  - moveDirection（当前移动方向）：{_text(player.move_direction)}",
        f"  - edgeProgressMs（路线边已推进毫秒）：{_optional_number(player.edge_progress_ms)}",
        f"  - edgeTotalMs（路线边总毫秒）：{_optional_number(player.edge_total_ms)}",
        f"  - verified（是否已完成宫门验核）：{_yes_no(player.verified)}",
        f"  - delivered（是否已完成终点交付）：{_yes_no(player.delivered)}",
        f"  - freshness（当前鲜度）：{player.freshness:.2f}",
        f"  - goodFruit（好果数量）：{player.good_fruit}",
        f"  - badFruit（坏果数量）：{player.bad_fruit}",
        f"  - guardActionPoint（设卡行动点）：{player.guard_action_point}",
        f"  - rushTacticUsedCount（已使用急策次数）：{player.rush_tactic_used_count}",
        f"  - breakOrderReady（破关令是否可用）：{_yes_no(player.break_order_ready)}",
        f"  - squadAvailable（可调度小分队人数）：{player.squad_available}",
        f"  - squadInFlight（已派出未归队小分队数量）：{player.squad_in_flight}",
        f"  - taskScore（皇榜任务累计分）：{player.task_score}",
        f"  - totalScore（当前总分）：{player.total_score}",
        f"  - resources（持有道具数量）：{_format_mapping(player.resources)}",
        f"  - buffs（当前增益状态）：{_format_iterable(player.buffs)}",
        f"  - currentProcess（正在处理的固定流程）：{_format_mapping(player.current_process)}",
    ]


def _render_node(node: PublicNodeSnapshot) -> list[str]:
    guard = node.guard
    return [
        f"- 节点 {node.node_id}：",
        f"  - nodeId（节点编号）：{node.node_id}",
        f"  - name（节点名称）：{_text(node.name)}",
        f"  - nodeType（节点类型）：{_text(node.node_type)}",
        f"  - hasObstacle（是否存在道路障碍）：{_yes_no(node.has_obstacle)}",
        f"  - obstacleType（障碍类型）：{_text(node.obstacle_type)}",
        f"  - obstacleOwner（障碍归属）：{_text(node.obstacle_owner)}",
        f"  - obstacleResidueRound（障碍残留影响轮数）：{_optional_number(node.obstacle_residue_round)}",
        f"  - resourceStock（节点可领取资源库存）：{_format_mapping(node.resource_stock)}",
        f"  - guard（节点设卡状态）：{_format_guard(guard)}",
        f"  - scouts（探路标记）：{_format_scouts(node.scouts)}",
    ]


def _render_task(task: PublicTaskSnapshot) -> list[str]:
    return [
        f"- 任务 {task.task_id or '无编号'}：",
        f"  - taskId（任务编号）：{_text(task.task_id)}",
        f"  - taskTemplateId（任务模板编号）：{_text(task.task_template_id)}",
        f"  - nodeId（任务目标节点）：{_text(task.node_id)}",
        f"  - score（完成得分）：{task.score}",
        f"  - processRound（任务处理轮数）：{task.process_round}",
        f"  - ownerPlayerId（当前领取玩家；0 或空表示无人领取）：{_optional_number(task.owner_player_id)}",
        f"  - protectionPlayerId（保护期归属玩家；0 或空表示无保护）：{_optional_number(task.protection_player_id)}",
        f"  - expireRound（过期轮次）：{_optional_number(task.expire_round)}",
        f"  - active（是否处于可见/可执行状态）：{_yes_no(task.active)}",
        f"  - completed（是否已完成）：{_yes_no(task.completed)}",
        f"  - failed（是否已失败）：{_yes_no(task.failed)}",
        f"  - status（中文状态）：{task.status}",
    ]


def _render_weather_group(title: str, items: list[dict[str, Any]]) -> list[str]:
    lines = [f"- {title}："]
    if not items:
        lines.append("  - 无。")
        return lines
    for index, weather in enumerate(items, start=1):
        lines.extend(
            [
                f"  - 第 {index} 条天气：",
                f"    - weatherId（天气编号）：{_text(weather.get('weatherId'))}",
                f"    - type（天气类型）：{_weather_type_name(weather.get('type'))}",
                f"    - region（影响区域）：{_route_type_name(weather.get('region'))}",
                f"    - remainRound（剩余轮数）：{_optional_number(weather.get('remainRound'))}",
                f"    - startRound（开始轮次）：{_optional_number(weather.get('startRound'))}",
                f"    - durationRound（持续轮数）：{_optional_number(weather.get('durationRound') or weather.get('duration'))}",
            ]
        )
        extra = _extra_fields(
            weather,
            {"weatherId", "type", "region", "remainRound", "startRound", "durationRound", "duration"},
        )
        if extra:
            lines.append(f"    - otherFields（其他天气字段）：{_format_mapping(extra)}")
    return lines


def _render_contest(contest: PublicContestSnapshot) -> list[str]:
    return [
        f"- 争夺 {contest.contest_id or '无编号'}：",
        f"  - contestId（窗口争夺编号）：{_text(contest.contest_id)}",
        f"  - targetNodeId（争夺目标节点）：{_text(contest.target_node_id)}",
        f"  - status（争夺状态）：{_text(contest.status)}",
        f"  - resolved（是否已结算）：{_yes_no(contest.resolved)}",
        f"  - winnerTeamId（胜方队伍）：{_text(contest.winner_team_id)}",
        f"  - participants（参赛玩家字段）：{_format_mapping(contest.participants)}",
    ]


def _render_event(event: PublicEventSnapshot) -> list[str]:
    return [
        f"- 事件 {event.event_type or 'UNKNOWN'}：",
        f"  - type（事件类型）：{_text(event.event_type)}",
        f"  - playerId（关联玩家）：{_optional_number(event.player_id)}",
        f"  - nodeId（关联节点）：{_text(event.node_id)}",
        f"  - targetNodeId（目标节点）：{_text(event.target_node_id)}",
        f"  - taskId（关联任务）：{_text(event.task_id)}",
        f"  - action（关联动作）：{_text(event.action)}",
        f"  - scoreDelta（分数变化）：{_optional_number(event.score_delta)}",
        f"  - errorCode（错误码）：{_text(event.error_code)}",
        f"  - message（服务器说明）：{_text(event.message)}",
        f"  - details（其他事件字段）：{_format_mapping(event.details)}",
    ]


def _render_action_result(result: PublicActionResultSnapshot) -> list[str]:
    return [
        f"- 动作结果 {result.action or 'UNKNOWN'}：",
        f"  - playerId（提交动作的玩家）：{_optional_number(result.player_id)}",
        f"  - action（动作类型）：{_text(result.action)}",
        f"  - accepted（服务器是否接受）：{_yes_no(result.accepted)}",
        f"  - result（结算结果）：{_text(result.result)}",
        f"  - errorCode（拒绝原因）：{_text(result.error_code)}",
        f"  - targetNodeId（动作目标节点）：{_text(result.target_node_id)}",
        f"  - resourceType（道具类型）：{_text(result.resource_type)}",
        f"  - taskId（任务编号）：{_text(result.task_id)}",
    ]


def _format_guard(guard: dict[str, Any]) -> str:
    if not guard:
        return "无设卡"
    fields = {
        "ownerTeamId": guard.get("ownerTeamId") or guard.get("teamId"),
        "defense": guard.get("defense"),
        "active": guard.get("active"),
        "completeRound": guard.get("completeRound"),
        "ageRound": guard.get("ageRound"),
    }
    fields = {key: value for key, value in fields.items() if value not in (None, "")}
    return _format_mapping(fields)


def _format_scouts(scouts: list[dict[str, Any]]) -> str:
    if not scouts:
        return "无探路标记"
    entries = []
    for index, scout in enumerate(scouts, start=1):
        entries.append(f"第{index}个标记：{_format_mapping(scout)}")
    return "；".join(entries)


def _format_mapping(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "无"
    parts = []
    for key in sorted(mapping):
        value = mapping[key]
        if value in (None, ""):
            continue
        parts.append(f"{key}={_format_value(value)}")
    return "，".join(parts) if parts else "无"


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return _yes_no(value)
    if isinstance(value, dict):
        return _format_mapping(value)
    if isinstance(value, list):
        return _format_iterable(value)
    if value is None or value == "":
        return "无"
    return str(value)


def _format_iterable(items: Iterable[Any]) -> str:
    values = list(items)
    if not values:
        return "无"
    rendered = []
    for value in values:
        if isinstance(value, dict):
            rendered.append(_format_mapping(value))
        else:
            rendered.append(str(value))
    return "，".join(rendered)


def _extra_fields(mapping: dict[str, Any], known_keys: set[str]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if key not in known_keys}


def _text(value: Any) -> str:
    if value is None or value == "":
        return "无"
    return str(value)


def _optional_number(value: Any) -> str:
    if value is None or value == "":
        return "无"
    return str(value)


def _yes_no(value: Any) -> str:
    if value is None:
        return "未知"
    return "是" if bool(value) else "否"


def _phase_name(phase: str) -> str:
    names = {
        "NORMAL": "NORMAL（常规阶段）",
        "RUSH": "RUSH（宫宴冲刺阶段）",
    }
    return names.get(phase, _text(phase))


def _state_name(state: str) -> str:
    names = {
        "IDLE": "IDLE（节点空闲，可提交节点动作）",
        "MOVING": "MOVING（路线边移动中）",
        "WAITING": "WAITING（等待中，需结合 nextNodeId 判断是否在路线边）",
        "PROCESSING": "PROCESSING（固定处理/任务处理中）",
        "CONTESTING": "CONTESTING（窗口争夺中）",
        "RESTING": "RESTING（休整中）",
        "FORCED_PASSING": "FORCED_PASSING（强制通行处理中）",
        "VERIFYING": "VERIFYING（宫门验核中）",
    }
    return names.get(state, _text(state))


def _route_type_name(route_type: Any) -> str:
    route_type_text = _text(route_type)
    names = {
        "ROAD": "ROAD（陆路）",
        "WATER": "WATER（水路）",
        "MOUNTAIN": "MOUNTAIN（山路）",
        "BRANCH": "BRANCH（支路）",
    }
    return names.get(route_type_text, route_type_text)


def _weather_type_name(weather_type: Any) -> str:
    weather_type_text = _text(weather_type)
    names = {
        "HEAVY_RAIN": "HEAVY_RAIN（暴雨）",
        "HOT": "HOT（高温）",
        "WIND": "WIND（大风）",
    }
    return names.get(weather_type_text, weather_type_text)
