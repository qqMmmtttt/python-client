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
        chosen_actions: list[dict[str, Any]] = []
        selected_strategies: list[str] = []
        used_categories: set[str] = set()
        for strategy in self._strategies:
            strategy_name = strategy.__class__.__name__
            actions = strategy.decide(context)
            self._logger.trace(
                "strategy_eval round=%s strategy=%s actions=%s",
                state.round_no,
                strategy_name,
                actions,
            )
            accepted_actions: list[dict[str, Any]] = []
            for action in actions:
                categories = _action_categories(action)
                if categories & used_categories:
                    self._logger.trace(
                        "strategy_skip round=%s strategy=%s action=%s used_categories=%s",
                        state.round_no,
                        strategy_name,
                        action,
                        sorted(used_categories),
                    )
                    continue
                used_categories.update(categories)
                chosen_actions.append(action)
                accepted_actions.append(action)
            if accepted_actions:
                selected_strategies.append(strategy_name)

        if chosen_actions:
            ordered_actions = sorted(chosen_actions, key=_action_order)
            self._logger.important(
                "decision round=%s strategy=%s categories=%s actions=%s",
                state.round_no,
                "+".join(selected_strategies),
                sorted(used_categories),
                ordered_actions,
            )
            return ordered_actions
        self._logger.important(
            "decision round=%s strategy=none actions=[]",
            state.round_no,
        )
        return []


SQUAD_ACTIONS = {"SQUAD_SCOUT", "SQUAD_CLEAR", "SQUAD_REINFORCE", "SQUAD_WEAKEN"}
WINDOW_ACTIONS = {"WINDOW_CARD"}
RUSH_ACTIONS = {"RUSH_SPEED", "RUSH_PROTECT"}


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
