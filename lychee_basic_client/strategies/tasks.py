from typing import Any

from lychee_basic_client.models.state import GameState
from lychee_basic_client.protocol.actions import claim_task

BUSY_STATES = {"MOVING", "PROCESSING", "CONTESTING", "RESTING", "FORCED_PASSING", "VERIFYING"}


class TaskStrategy:
    """Royal bulletin task selection and claiming decisions."""

    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        player = state.me
        if player is None or player.delivered or player.state in BUSY_STATES:
            return []
        if player.current_process or not player.current_node_id:
            return []
        if state.round_no >= 430:
            return []
        if player.current_node_id in {state.game_map.gate_node_id, *state.game_map.terminal_node_ids}:
            return []

        candidates = []
        for task in state.tasks:
            if not _can_claim_task(task, state.player_id):
                continue
            if task.get("nodeId") != player.current_node_id:
                continue
            candidates.append(task)

        if not candidates:
            return []

        candidates.sort(key=lambda task: int(task.get("score") or 0), reverse=True)
        return [claim_task(candidates[0]["taskId"])]
        return []


def _can_claim_task(task: dict[str, Any], player_id: int) -> bool:
    if not task.get("active", True):
        return False
    if task.get("completed") or task.get("failed"):
        return False

    owner = int(task.get("ownerPlayerId") or 0)
    if owner not in (0, player_id):
        return False

    protected = int(task.get("protectionPlayerId") or 0)
    if protected not in (0, player_id):
        return False
    return bool(task.get("taskId"))
