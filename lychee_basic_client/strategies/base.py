from typing import Any, Protocol

from lychee_basic_client.models.state import GameState


class Strategy(Protocol):
    def on_start(self, state: GameState) -> None:
        ...

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        ...


class NoopStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        return []

