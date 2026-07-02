from typing import Any

from lychee_basic_client.planning.tasks import (
    BONUS_TASK_SCORE_GOAL,
    find_claimable_task_here,
    should_pursue_tasks,
)
from lychee_basic_client.protocol.actions import claim_task
from lychee_basic_client.strategies.context import StrategyContext

BUSY_STATES = {"MOVING", "PROCESSING", "CONTESTING", "RESTING", "FORCED_PASSING", "VERIFYING"}


class TaskStrategy:
    """Royal bulletin task selection and claiming decisions."""

    def on_start(self, state: Any) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None or player.delivered or player.state in BUSY_STATES:
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

        task = find_claimable_task_here(state)
        if task is None:
            return []
        return [claim_task(task["taskId"])]
