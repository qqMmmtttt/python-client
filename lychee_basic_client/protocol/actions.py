from typing import Any, Optional


def action_message(
    match_id: str, round_no: int, player_id: int, actions: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "msg_name": "action",
        "msg_data": {
            "matchId": match_id,
            "round": round_no,
            "playerId": player_id,
            "actions": actions,
        },
    }


def wait() -> dict[str, Any]:
    return {"action": "WAIT"}


def move(target_node_id: str) -> dict[str, Any]:
    return {"action": "MOVE", "targetNodeId": target_node_id}


def process(target_node_id: Optional[str] = None) -> dict[str, Any]:
    action: dict[str, Any] = {"action": "PROCESS"}
    if target_node_id is not None:
        action["targetNodeId"] = target_node_id
    return action


def dock(target_node_id: Optional[str] = None) -> dict[str, Any]:
    action: dict[str, Any] = {"action": "DOCK"}
    if target_node_id is not None:
        action["targetNodeId"] = target_node_id
    return action


def deliver() -> dict[str, Any]:
    return {"action": "DELIVER"}


def verify_gate(target_node_id: Optional[str] = None, rush_tactic: Optional[str] = None) -> dict[str, Any]:
    action: dict[str, Any] = {"action": "VERIFY_GATE"}
    if target_node_id is not None:
        action["targetNodeId"] = target_node_id
    if rush_tactic is not None:
        action["rushTactic"] = rush_tactic
    return action


def claim_resource(target_node_id: str, resource_type: str) -> dict[str, Any]:
    return {
        "action": "CLAIM_RESOURCE",
        "targetNodeId": target_node_id,
        "resourceType": resource_type,
    }


def use_resource(resource_type: str, target_node_id: Optional[str] = None) -> dict[str, Any]:
    action: dict[str, Any] = {"action": "USE_RESOURCE", "resourceType": resource_type}
    if target_node_id is not None:
        action["targetNodeId"] = target_node_id
    return action


def claim_task(task_id: str) -> dict[str, Any]:
    return {"action": "CLAIM_TASK", "taskId": task_id}


def clear(target_node_id: str) -> dict[str, Any]:
    return {"action": "CLEAR", "targetNodeId": target_node_id}


def set_guard(target_node_id: str, extra_good_fruit: Optional[int] = None) -> dict[str, Any]:
    action: dict[str, Any] = {"action": "SET_GUARD", "targetNodeId": target_node_id}
    if extra_good_fruit is not None:
        action["extraGoodFruit"] = extra_good_fruit
    return action


def break_guard(
    target_node_id: str,
    good_fruit: Optional[int] = None,
    bad_fruit: Optional[int] = None,
    rush_tactic: Optional[str] = None,
) -> dict[str, Any]:
    action: dict[str, Any] = {"action": "BREAK_GUARD", "targetNodeId": target_node_id}
    if good_fruit is not None:
        action["goodFruit"] = good_fruit
    if bad_fruit is not None:
        action["badFruit"] = bad_fruit
    if rush_tactic is not None:
        action["rushTactic"] = rush_tactic
    return action


def forced_pass(target_node_id: str) -> dict[str, Any]:
    return {"action": "FORCED_PASS", "targetNodeId": target_node_id}


def window_card(contest_id: str, card: str, rush_tactic: Optional[str] = None) -> dict[str, Any]:
    action: dict[str, Any] = {
        "action": "WINDOW_CARD",
        "contestId": contest_id,
        "card": card,
    }
    if rush_tactic is not None:
        action["rushTactic"] = rush_tactic
    return action


def squad_scout(target_node_id: str) -> dict[str, Any]:
    return {"action": "SQUAD_SCOUT", "targetNodeId": target_node_id}


def squad_clear(target_node_id: str) -> dict[str, Any]:
    return {"action": "SQUAD_CLEAR", "targetNodeId": target_node_id}


def squad_reinforce(target_node_id: str) -> dict[str, Any]:
    return {"action": "SQUAD_REINFORCE", "targetNodeId": target_node_id}


def squad_weaken(target_node_id: str) -> dict[str, Any]:
    return {"action": "SQUAD_WEAKEN", "targetNodeId": target_node_id}


def rush_speed() -> dict[str, Any]:
    return {"action": "RUSH_SPEED"}


def rush_protect() -> dict[str, Any]:
    return {"action": "RUSH_PROTECT"}

