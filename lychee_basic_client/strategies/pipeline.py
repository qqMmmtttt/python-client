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
        for strategy in self._strategies:
            strategy_name = strategy.__class__.__name__
            actions = strategy.decide(context)
            self._logger.trace(
                "strategy_eval round=%s strategy=%s actions=%s",
                state.round_no,
                strategy_name,
                actions,
            )
            if actions:
                self._logger.important(
                    "decision round=%s strategy=%s actions=%s",
                    state.round_no,
                    strategy_name,
                    actions,
                )
                return actions
        self._logger.important(
            "decision round=%s strategy=none actions=[]",
            state.round_no,
        )
        return []
