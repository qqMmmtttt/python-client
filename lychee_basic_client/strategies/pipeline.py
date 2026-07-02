from typing import Any

from lychee_basic_client.models.state import GameState

from .base import Strategy


class StrategyPipeline:
    def __init__(self, strategies: list[Strategy]) -> None:
        self._strategies = strategies

    def on_start(self, state: GameState) -> None:
        for strategy in self._strategies:
            strategy.on_start(state)

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        for strategy in self._strategies:
            actions = strategy.decide(state)
            if actions:
                return actions
        return []

