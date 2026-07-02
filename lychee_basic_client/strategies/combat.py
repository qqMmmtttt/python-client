from typing import Any

from lychee_basic_client.protocol.actions import window_card
from lychee_basic_client.strategies.context import StrategyContext


class CombatStrategy:
    """Window, guard, forced-pass, squad, and rush-tactic decisions."""

    def on_start(self, state: Any) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None:
            return []
        for contest in state.contests:
            if contest.get("resolved") or contest.get("status") == "SUPPRESSED":
                continue
            if _contest_involves_player(contest, state.player_id):
                return [window_card(contest["contestId"], _choose_card(player.raw))]
        return []


def _contest_involves_player(contest: dict[str, Any], player_id: int) -> bool:
    player_fields = [
        "redPlayerId",
        "bluePlayerId",
        "initiatorPlayerId",
    ]
    return any(contest.get(field) == player_id for field in player_fields)


def _choose_card(player: dict[str, Any]) -> str:
    resources = player.get("resources") or {}
    if int(player.get("guardActionPoint") or 0) > 0:
        return "BING_ZHENG"
    if float(player.get("freshness") or 0) >= 80 and int(player.get("goodFruit") or 0) > 20:
        return "XIAN_GONG"
    if resources.get("PASS_TOKEN", 0) > 0 or resources.get("OFFICIAL_PERMIT", 0) > 0:
        return "YAN_DIE"
    if _has_speed_payment(player):
        return "QIANG_XING"
    return "ABSTAIN"


def _has_speed_payment(player: dict[str, Any]) -> bool:
    resources = player.get("resources") or {}
    if resources.get("FAST_HORSE", 0) > 0 or resources.get("SHORT_HORSE", 0) > 0:
        return True
    for buff in player.get("buffs") or []:
        if buff.get("type") in {"FAST_HORSE", "SHORT_HORSE", "RUSH_SPEED"}:
            return True
    return False
