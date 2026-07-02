from dataclasses import dataclass
from typing import Any, Optional

from lychee_basic_client.models.state import GameState
from lychee_basic_client.planning.estimates import estimate_delivery_rounds, estimate_path_rounds

TASK_SCORE_GOAL = 90
BONUS_TASK_SCORE_GOAL = 110
TASK_CUTOFF_ROUND = 390
DELIVERY_SAFETY_MARGIN = 55

HIGH_VALUE_TEMPLATES = {"T01", "T02", "T04", "T06", "T08", "T11"}
TASK_TEMPLATE_PRIORITY = {
    "T01": 100,
    "T02": 95,
    "T11": 90,
    "T04": 86,
    "T08": 82,
    "T06": 78,
    "T12": 45,
    "T13": 42,
    "T14": 40,
}


@dataclass(frozen=True)
class TaskTarget:
    task: dict[str, Any]
    stand_node_id: str
    score: int
    estimated_rounds: int

    @property
    def task_id(self) -> str:
        return str(self.task.get("taskId") or "")

    @property
    def template_id(self) -> str:
        return str(self.task.get("taskTemplateId") or "")


def should_pursue_tasks(state: GameState, current_node_id: str) -> bool:
    player = state.me
    if player is None:
        return False
    if player.task_score >= BONUS_TASK_SCORE_GOAL:
        return False
    if state.round_no >= TASK_CUTOFF_ROUND:
        return False

    delivery_rounds = estimate_delivery_rounds(state, current_node_id, player.verified)
    return state.round_no + delivery_rounds + DELIVERY_SAFETY_MARGIN < 600


def find_claimable_task_here(state: GameState) -> Optional[dict[str, Any]]:
    player = state.me
    if player is None or not player.current_node_id:
        return None

    candidates = []
    for task in state.tasks:
        if not is_task_available(task, state.player_id, state.round_no):
            continue
        stand_nodes = task_stand_nodes(state, task)
        if player.current_node_id not in stand_nodes:
            continue
        if not is_task_affordable(state, task):
            continue
        candidates.append(task)

    if not candidates:
        return None
    candidates.sort(key=lambda task: _task_sort_key(state, task), reverse=True)
    return candidates[0]


def select_task_target(state: GameState, current_node_id: str) -> Optional[TaskTarget]:
    if not should_pursue_tasks(state, current_node_id):
        return None

    candidates: list[TaskTarget] = []
    for task in state.tasks:
        if not is_task_available(task, state.player_id, state.round_no):
            continue
        if not is_task_affordable(state, task):
            continue
        target = _best_stand_node_for_task(state, current_node_id, task)
        if target is None:
            continue
        if not _task_has_safe_timing(state, task, target):
            continue
        candidates.append(target)

    if not candidates:
        return None

    candidates.sort(key=lambda target: _target_sort_key(state, target), reverse=True)
    return candidates[0]


def find_t04_for_obstacle(state: GameState, obstacle_node_id: str) -> Optional[dict[str, Any]]:
    player = state.me
    if player is None or not player.current_node_id:
        return None
    if player.current_node_id not in {obstacle_node_id, *state.game_map.neighbors(obstacle_node_id)}:
        return None

    for task in state.tasks:
        if str(task.get("taskTemplateId") or "") != "T04":
            continue
        if task.get("nodeId") != obstacle_node_id:
            continue
        if is_task_available(task, state.player_id, state.round_no):
            return task
    return None


def is_task_available(task: dict[str, Any], player_id: int, round_no: int) -> bool:
    if not task.get("taskId"):
        return False
    if not task.get("active", True):
        return False
    if task.get("completed") or task.get("failed"):
        return False

    expire_round = int(task.get("expireRound") or 0)
    if expire_round and expire_round <= round_no + 2:
        return False

    owner = int(task.get("ownerPlayerId") or 0)
    if owner not in (0, player_id):
        return False

    protected = int(task.get("protectionPlayerId") or 0)
    if protected not in (0, player_id):
        return False
    return True


def is_task_affordable(state: GameState, task: dict[str, Any]) -> bool:
    template_id = str(task.get("taskTemplateId") or "")
    player = state.me
    if player is None:
        return False
    if template_id == "T06":
        return player.resources.get("FAST_HORSE", 0) + player.resources.get("SHORT_HORSE", 0) > 0
    return True


def task_stand_nodes(state: GameState, task: dict[str, Any]) -> set[str]:
    node_id = task.get("nodeId")
    if not node_id:
        return set()
    if str(task.get("taskTemplateId") or "") == "T04":
        return {node_id, *state.game_map.neighbors(node_id)}
    return {node_id}


def task_score(task: dict[str, Any]) -> int:
    return int(task.get("score") or _default_task_score(str(task.get("taskTemplateId") or "")))


def _best_stand_node_for_task(
    state: GameState, current_node_id: str, task: dict[str, Any]
) -> Optional[TaskTarget]:
    best: Optional[TaskTarget] = None
    for stand_node_id in task_stand_nodes(state, task):
        path = state.game_map.fastest_path(current_node_id, stand_node_id)
        if not path:
            continue
        estimated = estimate_path_rounds(state, path)
        candidate = TaskTarget(
            task=task,
            stand_node_id=stand_node_id,
            score=task_score(task),
            estimated_rounds=estimated,
        )
        if best is None or candidate.estimated_rounds < best.estimated_rounds:
            best = candidate
    return best


def _task_has_safe_timing(state: GameState, task: dict[str, Any], target: TaskTarget) -> bool:
    process_round = int(task.get("processRound") or 5)
    finish_round = state.round_no + target.estimated_rounds + process_round
    expire_round = int(task.get("expireRound") or 0)
    if expire_round and finish_round > expire_round:
        return False

    player = state.me
    verified = player.verified if player else False
    delivery_rounds = estimate_delivery_rounds(state, target.stand_node_id, verified)
    return finish_round + delivery_rounds + DELIVERY_SAFETY_MARGIN < 600


def _target_sort_key(state: GameState, target: TaskTarget) -> tuple[int, int, int, int]:
    template_id = target.template_id
    score = target.score
    if state.me and state.me.task_score >= TASK_SCORE_GOAL and template_id not in HIGH_VALUE_TEMPLATES:
        score -= 8
    return (
        score,
        TASK_TEMPLATE_PRIORITY.get(template_id, 0),
        -target.estimated_rounds,
        -int(target.task.get("expireRound") or 9999),
    )


def _task_sort_key(state: GameState, task: dict[str, Any]) -> tuple[int, int, int]:
    template_id = str(task.get("taskTemplateId") or "")
    return (
        task_score(task),
        TASK_TEMPLATE_PRIORITY.get(template_id, 0),
        -int(task.get("processRound") or 0),
    )


def _default_task_score(template_id: str) -> int:
    if template_id in HIGH_VALUE_TEMPLATES:
        return 30
    if template_id in {"T12", "T13", "T14"}:
        return 15
    return 0
