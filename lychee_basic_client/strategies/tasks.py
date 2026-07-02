from typing import Any

from lychee_basic_client.planning.tasks import (
    BONUS_TASK_SCORE_GOAL,
    find_claimable_task_here,
    should_pursue_tasks,
)
from lychee_basic_client.protocol.actions import claim_task
from lychee_basic_client.rules.states import MAIN_ACTION_BUSY_STATES
from lychee_basic_client.strategies.context import StrategyContext


class TaskStrategy:
    """Royal bulletin task selection and claiming decisions."""

    def __init__(self) -> None:
        self._rejected_task_ids: set[str] = set()

    def on_start(self, state: Any) -> None:
        self._rejected_task_ids.clear()
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        self._observe_rejections(context)
        player = state.me
        if player is None or player.delivered or player.state in MAIN_ACTION_BUSY_STATES:
            return []
        if player.current_process or not player.current_node_id:
            return []
        if player.task_score >= BONUS_TASK_SCORE_GOAL:
            return []
        if state.round_no >= 430:
            return []
        if player.current_node_id in {state.game_map.gate_node_id, *state.game_map.terminal_node_ids}:
            return []
        if not should_pursue_tasks(state, player.current_node_id):
            return []

        task = find_claimable_task_here(state, self._rejected_task_ids)
        if task is None:
            return []
        return [claim_task(task["taskId"])]

    def _observe_rejections(self, context: StrategyContext) -> None:
        for rejected in context.events.rejected_actions:
            if rejected.action != "CLAIM_TASK":
                continue
            task_id = _rejected_task_id(rejected.raw)
            if task_id:
                self._rejected_task_ids.add(task_id)


def _rejected_task_id(raw: dict[str, Any]) -> str:
    payload = raw.get("payload") or raw
    return str(payload.get("taskId") or "")
