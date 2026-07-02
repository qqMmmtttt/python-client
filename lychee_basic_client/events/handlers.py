from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class RejectedAction:
    action: str
    error_code: str
    source: str = "event"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventSummary:
    completed_process_nodes: set[str] = field(default_factory=set)
    completed_task_ids: set[str] = field(default_factory=set)
    cleared_obstacle_nodes: set[str] = field(default_factory=set)
    verified_gate: bool = False
    delivered: bool = False
    rejected_actions: list[RejectedAction] = field(default_factory=list)


def summarize_events(
    events: list[dict[str, Any]],
    player_id: int,
    action_results: Optional[list[dict[str, Any]]] = None,
) -> EventSummary:
    completed_process_nodes: set[str] = set()
    completed_task_ids: set[str] = set()
    cleared_obstacle_nodes: set[str] = set()
    verified_gate = False
    delivered = False
    rejected_actions: list[RejectedAction] = []

    for event in events:
        payload = event.get("payload") or {}
        event_player_id = payload.get("playerId")
        if event_player_id not in (None, player_id):
            continue

        event_type = event.get("type")
        if event_type == "PROCESS_COMPLETE":
            if _is_fixed_process_completion(payload):
                node_id = payload.get("nodeId") or payload.get("targetNodeId")
                if node_id:
                    completed_process_nodes.add(node_id)
        elif event_type == "TASK_COMPLETE":
            task_id = payload.get("taskId")
            if task_id:
                completed_task_ids.add(task_id)
        elif event_type == "OBSTACLE_CLEAR":
            node_id = payload.get("nodeId") or payload.get("targetNodeId")
            if node_id:
                cleared_obstacle_nodes.add(node_id)
        elif event_type in {"VERIFY_GATE_COMPLETE", "VERIFY_GATE_ALREADY_DONE"}:
            verified_gate = True
        elif event_type == "DELIVER_SUCCESS":
            delivered = True
        elif event_type in {"ACTION_REJECTED", "INVALID_ACTION"}:
            rejected_actions.append(
                RejectedAction(
                    action=str(payload.get("action") or ""),
                    error_code=str(payload.get("errorCode") or ""),
                    source="event",
                    raw=event,
                )
            )

    for result in action_results or []:
        if result.get("playerId") != player_id:
            continue
        if result.get("accepted", True):
            continue
        rejected_actions.append(
            RejectedAction(
                action=str(result.get("action") or ""),
                error_code=str(result.get("errorCode") or result.get("result") or ""),
                source="actionResult",
                raw=result,
            )
        )

    return EventSummary(
        completed_process_nodes=completed_process_nodes,
        completed_task_ids=completed_task_ids,
        cleared_obstacle_nodes=cleared_obstacle_nodes,
        verified_gate=verified_gate,
        delivered=delivered,
        rejected_actions=rejected_actions,
    )


def _is_fixed_process_completion(payload: dict[str, Any]) -> bool:
    action = str(payload.get("action") or "").upper()
    object_key = str(payload.get("objectKey") or "").upper()
    if action in {"CLAIM_TASK", "CLAIM_RESOURCE", "CLEAR", "VERIFY_GATE", "FORCED_PASS"}:
        return False
    if object_key.startswith(("TASK:", "RESOURCE:", "OBSTACLE:", "GATE:", "PASS:", "GUARD:")):
        return False
    return True
