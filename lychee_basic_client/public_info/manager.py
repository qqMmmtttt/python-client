from collections import deque
from typing import Optional

from lychee_basic_client.models.state import GameState

from .snapshot import PublicRoundSnapshot


class PublicInformationManager:
    """维护最近若干轮公开状态，后续策略可从这里读取统一上下文。"""

    def __init__(self, max_history: int = 120) -> None:
        self._history: deque[PublicRoundSnapshot] = deque(maxlen=max_history)

    @property
    def latest(self) -> Optional[PublicRoundSnapshot]:
        if not self._history:
            return None
        return self._history[-1]

    @property
    def history(self) -> tuple[PublicRoundSnapshot, ...]:
        return tuple(self._history)

    def update(self, state: GameState) -> PublicRoundSnapshot:
        snapshot = PublicRoundSnapshot.from_state(state)
        self._history.append(snapshot)
        return snapshot

    def clear(self) -> None:
        self._history.clear()
