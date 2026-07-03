from typing import Any


FORCE_EMPTY_ACTION = "__FORCE_EMPTY_ACTIONS__"


def force_empty_actions(reason: str, **details: Any) -> dict[str, Any]:
    action: dict[str, Any] = {"action": FORCE_EMPTY_ACTION, "reason": reason}
    action.update(details)
    return action


def is_force_empty_action(action: dict[str, Any]) -> bool:
    return action.get("action") == FORCE_EMPTY_ACTION
