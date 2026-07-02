from typing import Any

from lychee_basic_client.models.state import GameState

from .base import Strategy
from .context import StrategyContext


class StrategyPipeline:
    def __init__(self, strategies: list[Strategy]) -> None:
        self._strategies = strategies

    def on_start(self, state: GameState) -> None:
        for strategy in self._strategies:
            strategy.on_start(state)

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        context = StrategyContext.from_state(state)
        for strategy in self._strategies:
            actions = strategy.decide(context)
            if actions:
                return actions
        return []
