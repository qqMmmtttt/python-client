from typing import Any, Protocol

from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.context import StrategyContext


class Strategy(Protocol):
    def on_start(self, state: GameState) -> None:
        ...

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        ...


class NoopStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return []
