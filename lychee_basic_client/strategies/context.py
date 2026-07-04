from dataclasses import dataclass

from lychee_basic_client.events.handlers import EventSummary, summarize_events
from lychee_basic_client.models.state import GameState
from lychee_basic_client.public_info.snapshot import PublicRoundSnapshot


@dataclass(frozen=True)
class StrategyContext:
    state: GameState
    events: EventSummary
    public_info: PublicRoundSnapshot

    @classmethod
    def from_state(cls, state: GameState) -> "StrategyContext":
        return cls(
            state=state,
            events=summarize_events(state.events, state.player_id, state.action_results),
            public_info=PublicRoundSnapshot.from_state(state),
        )
