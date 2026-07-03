from typing import Any

from lychee_basic_client.models.state import GameState
from lychee_basic_client.observability.logging_setup import get_logger

from .base import Strategy
from .context import StrategyContext


class StrategyPipeline:
    def __init__(self, strategies: list[Strategy]) -> None:
        self._strategies = strategies
        self._logger = get_logger("strategies.pipeline")

    def on_start(self, state: GameState) -> None:
        for strategy in self._strategies:
            strategy.on_start(state)

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        context = StrategyContext.from_state(state)
        chosen_actions: list[ChosenAction] = []
        for strategy in self._strategies:
            strategy_name = strategy.__class__.__name__
            actions = strategy.decide(context)
            self._logger.trace(
                "strategy_eval round=%s strategy=%s actions=%s",
                state.round_no,
                strategy_name,
                actions,
            )
            for action in actions:
                categories = _action_categories(action)
                priority = _action_priority(action)
                conflicts = [
                    chosen
                    for chosen in chosen_actions
                    if categories & chosen.categories
                ]
                if conflicts and priority <= max(chosen.priority for chosen in conflicts):
                    self._logger.trace(
                        "strategy_skip round=%s strategy=%s action=%s used_categories=%s",
                        state.round_no,
                        strategy_name,
                        action,
                        sorted({category for chosen in conflicts for category in chosen.categories}),
                    )
                    continue
                if conflicts:
                    self._logger.trace(
                        "strategy_replace round=%s strategy=%s action=%s replaced=%s",
                        state.round_no,
                        strategy_name,
                        action,
                        [chosen.action for chosen in conflicts],
                    )
                chosen_actions = [
                    chosen
                    for chosen in chosen_actions
                    if not (categories & chosen.categories)
                ]
                chosen_actions.append(
                    ChosenAction(
                        action=action,
                        categories=categories,
                        priority=priority,
                        strategy_name=strategy_name,
                    )
                )

        if chosen_actions:
            ordered = sorted(chosen_actions, key=lambda chosen: _action_order(chosen.action))
            ordered_actions = [chosen.action for chosen in ordered]
            used_categories = {
                category
                for chosen in chosen_actions
                for category in chosen.categories
            }
            self._logger.important(
                "decision round=%s strategy=%s categories=%s actions=%s",
                state.round_no,
                "+".join(chosen.strategy_name for chosen in ordered),
                sorted(used_categories),
                ordered_actions,
            )
            return ordered_actions
        self._logger.important(
            "decision round=%s strategy=none actions=[]",
            state.round_no,
        )
        return []


class ChosenAction:
    def __init__(
        self,
        action: dict[str, Any],
        categories: set[str],
        priority: int,
        strategy_name: str,
    ) -> None:
        self.action = action
        self.categories = categories
        self.priority = priority
        self.strategy_name = strategy_name


SQUAD_ACTIONS = {"SQUAD_SCOUT", "SQUAD_CLEAR", "SQUAD_REINFORCE", "SQUAD_WEAKEN"}
WINDOW_ACTIONS = {"WINDOW_CARD"}
RUSH_ACTIONS = {"RUSH_SPEED", "RUSH_PROTECT"}
RESOURCE_PRIORITY = {
    "ICE_BOX": 96,
    "FAST_HORSE": 95,
    "SHORT_HORSE": 94,
    "INTEL": 30,
}
RESOURCE_CLAIM_PRIORITY = {
    "ICE_BOX": 99,
    "FAST_HORSE": 98,
    "SHORT_HORSE": 97,
    "PASS_TOKEN": 95,
    "OFFICIAL_PERMIT": 95,
    "INTEL": 91,
    "BOAT_RIGHT": 89,
}


def _action_categories(action: dict[str, Any]) -> set[str]:
    action_type = str(action.get("action") or "")
    if action_type in SQUAD_ACTIONS:
        categories = {"squad"}
    elif action_type in WINDOW_ACTIONS:
        categories = {"window"}
    elif action_type in RUSH_ACTIONS:
        categories = {"main", "rush"}
    else:
        categories = {"main"}

    if action.get("rushTactic"):
        categories.add("rush")
    return categories


def _action_order(action: dict[str, Any]) -> int:
    categories = _action_categories(action)
    if "main" in categories:
        return 0
    if "squad" in categories:
        return 1
    if "window" in categories:
        return 2
    return 3


def _action_priority(action: dict[str, Any]) -> int:
    action_type = str(action.get("action") or "")
    if action_type == "DELIVER":
        return 130
    if action_type == "VERIFY_GATE":
        return 120
    if action_type in {"FORCED_PASS", "CLEAR", "BREAK_GUARD"}:
        return 115
    if action_type == "PROCESS":
        return 105
    if action_type == "CLAIM_TASK":
        return 100
    if action_type == "SET_GUARD":
        return 92
    if action_type == "CLAIM_RESOURCE":
        return RESOURCE_CLAIM_PRIORITY.get(str(action.get("resourceType") or ""), 80)
    if action_type == "MOVE":
        return 90
    if action_type == "RUSH_SPEED":
        return 97
    if action_type == "RUSH_PROTECT":
        return 97
    if action_type == "USE_RESOURCE":
        return RESOURCE_PRIORITY.get(str(action.get("resourceType") or ""), 40)
    if action_type in SQUAD_ACTIONS:
        return 70
    if action_type in WINDOW_ACTIONS:
        return 70
    return 50
