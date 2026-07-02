from typing import Any

from lychee_basic_client.models.state import GameState
from lychee_basic_client.protocol.actions import window_card


class CombatStrategy:
    """Window, guard, forced-pass, squad, and rush-tactic decisions."""

    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, state: GameState) -> list[dict[str, Any]]:
        for contest in state.contests:
            if contest.get("resolved") or contest.get("status") == "SUPPRESSED":
                continue
            if _contest_involves_player(contest, state.player_id):
                return [window_card(contest["contestId"], "ABSTAIN")]
        return []


def _contest_involves_player(contest: dict[str, Any], player_id: int) -> bool:
    player_fields = [
        "redPlayerId",
        "bluePlayerId",
        "initiatorPlayerId",
    ]
    return any(contest.get(field) == player_id for field in player_fields)
