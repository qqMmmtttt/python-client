from typing import Any, Optional

from lychee_basic_client.observability.logging_setup import get_logger
from lychee_basic_client.protocol.actions import window_card
from lychee_basic_client.rules.buffs import has_move_buff
from lychee_basic_client.strategies.context import StrategyContext


# 同一争夺对象连续平局达到此次数后，我方放弃争夺（出 ABSTAIN），避免与对手策略相同时无限平局循环
DRAW_LIMIT_PER_TARGET = 2


class CombatStrategy:
    """Window, guard, forced-pass, squad, and rush-tactic decisions."""

    def __init__(self) -> None:
        self._logger = get_logger("strategies.combat")
        self._draw_counts: dict[str, int] = {}
        self._seen_contest_ids: set[str] = set()

    def on_start(self, state: Any) -> None:
        self._draw_counts.clear()
        self._seen_contest_ids.clear()
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        state = context.state
        player = state.me
        if player is None:
            return []
        self._update_draw_counts(state)
        for contest in state.contests:
            if contest.get("resolved") or contest.get("status") == "SUPPRESSED":
                continue
            if _contest_involves_player(contest, state.player_id):
                target_node = str(contest.get("targetNodeId") or "")
                opponent_card = _get_opponent_last_card(
                    contest, state.player_id, player.team_id
                )
                if target_node and self._draw_counts.get(target_node, 0) >= DRAW_LIMIT_PER_TARGET:
                    card = "ABSTAIN"
                    self._logger.important(
                        "window_card_abstain_draw_limit round=%s contest=%s node=%s draws=%s"
                        " | 窗口出牌：同一对象连续平局达上限，放弃争夺避免无限循环",
                        state.round_no,
                        contest.get("contestId"),
                        target_node,
                        self._draw_counts.get(target_node, 0),
                    )
                else:
                    card = _choose_card(
                        player.raw, contest, state.player_id, player.team_id
                    )
                    self._logger.important(
                        "window_card round=%s contest=%s type=%s roundIndex=%s card=%s opponent_last=%s"
                        " | 窗口出牌：本队参与窗口争夺，按规则选择本拍窗口牌（3 拍定胜负）",
                        state.round_no,
                        contest.get("contestId"),
                        contest.get("contestType") or contest.get("type"),
                        contest.get("roundIndex"),
                        card,
                        opponent_card,
                    )
                return [window_card(contest["contestId"], card)]
        return []

    def _update_draw_counts(self, state: Any) -> None:
        """扫描已结算的 contest，更新各对象的连续平局计数；产生胜方时重置。"""
        for contest in state.contests:
            if not contest.get("resolved"):
                continue
            contest_id = str(contest.get("contestId") or "")
            if not contest_id or contest_id in self._seen_contest_ids:
                continue
            self._seen_contest_ids.add(contest_id)
            target_node = str(contest.get("targetNodeId") or "")
            if not target_node:
                continue
            winner = str(contest.get("winnerTeamId") or "")
            if winner == "DRAW":
                self._draw_counts[target_node] = self._draw_counts.get(target_node, 0) + 1
            else:
                self._draw_counts[target_node] = 0


def _contest_involves_player(contest: dict[str, Any], player_id: int) -> bool:
    player_fields = [
        "redPlayerId",
        "bluePlayerId",
        "initiatorPlayerId",
    ]
    return any(contest.get(field) == player_id for field in player_fields)


# 胜负表：我方 a 对手 b → 胜/负/平
# | 我方 \ 对方 | YAN_DIE | QIANG_XING | XIAN_GONG | BING_ZHENG |
# | YAN_DIE     | 平      | 胜         | 负        | 负         |
# | QIANG_XING  | 负      | 平         | 胜        | 负         |
# | XIAN_GONG   | 胜      | 负         | 平        | 胜         |
# | BING_ZHENG  | 胜      | 胜         | 负        | 平         |

# 克制关系：对手出 X → 我方应出 _COUNTER[X]（能胜）
_COUNTER = {
    "YAN_DIE": "XIAN_GONG",
    "QIANG_XING": "YAN_DIE",
    "XIAN_GONG": "QIANG_XING",
    "BING_ZHENG": "XIAN_GONG",
}

# 平局牌：对手出 X → 我方出同牌平局
_DRAW = {
    "YAN_DIE": "YAN_DIE",
    "QIANG_XING": "QIANG_XING",
    "XIAN_GONG": "XIAN_GONG",
    "BING_ZHENG": "BING_ZHENG",
}


def _choose_card(
    player: dict[str, Any],
    contest: dict[str, Any],
    my_player_id: int,
    my_team_id: str,
) -> str:
    contest_type = str(contest.get("contestType") or contest.get("type") or "")
    round_index = int(contest.get("roundIndex") or 0)
    opponent_card = _get_opponent_last_card(contest, my_player_id, my_team_id)

    # 第 2-3 拍：根据对手上一拍出牌选择克制牌
    if opponent_card and round_index > 1:
        counter = _counter_card(opponent_card, player)
        if counter:
            return counter

    # 第 1 拍或无克制牌可用：按默认策略出牌
    return _default_card(player, contest_type)


def _get_opponent_player_id(
    contest: dict[str, Any], my_player_id: int
) -> Optional[int]:
    red = contest.get("redPlayerId")
    blue = contest.get("bluePlayerId")
    if red == my_player_id:
        return blue
    if blue == my_player_id:
        return red
    return None


def _get_opponent_last_card(
    contest: dict[str, Any], my_player_id: int, my_team_id: str
) -> Optional[str]:
    """从 contest 的 cards 字段获取对手上一拍的出牌。"""
    cards = contest.get("cards") or {}
    if not cards:
        return None
    opp_player_id = _get_opponent_player_id(contest, my_player_id)
    if opp_player_id is not None:
        card = cards.get(str(opp_player_id))
        if card:
            return str(card)
    opp_team_id = "BLUE" if my_team_id == "RED" else "RED"
    card = cards.get(opp_team_id)
    if card:
        return str(card)
    for key, value in cards.items():
        if key != str(my_player_id) and key != my_team_id:
            return str(value)
    return None


def _counter_card(opponent_card: str, player: dict[str, Any]) -> Optional[str]:
    """根据对手上一拍出牌选择克制牌；成本不足则选平局牌；再不足返回 None。"""
    desired = _COUNTER.get(opponent_card)
    if desired and _can_play(desired, player):
        return desired
    draw = _DRAW.get(opponent_card)
    if draw and _can_play(draw, player):
        return draw
    return None


def _can_play(card: str, player: dict[str, Any]) -> bool:
    if card == "ABSTAIN":
        return True
    if card == "BING_ZHENG":
        return int(player.get("guardActionPoint") or 0) > 0
    if card == "XIAN_GONG":
        return (
            float(player.get("freshness") or 0) >= 80
            and int(player.get("goodFruit") or 0) > 0
        )
    if card == "YAN_DIE":
        resources = player.get("resources") or {}
        return resources.get("PASS_TOKEN", 0) > 0 or resources.get("OFFICIAL_PERMIT", 0) > 0
    if card == "QIANG_XING":
        return _has_speed_payment(player)
    return False


def _default_card(player: dict[str, Any], contest_type: str) -> str:
    """第 1 拍默认出牌策略。

    优先出 XIAN_GONG：献贡胜验牒和兵争（对手 critical 类型常出兵争），只消耗 1 篓好果；
    其次 BING_ZHENG（胜验牒和强行）；再依次尝试验牒、强行。
    """
    if _can_play("XIAN_GONG", player):
        return "XIAN_GONG"
    if _can_play("BING_ZHENG", player):
        return "BING_ZHENG"
    if _can_play("YAN_DIE", player):
        return "YAN_DIE"
    if _can_play("QIANG_XING", player):
        return "QIANG_XING"
    return "ABSTAIN"


def _has_speed_payment(player: dict[str, Any]) -> bool:
    resources = player.get("resources") or {}
    if resources.get("FAST_HORSE", 0) > 0 or resources.get("SHORT_HORSE", 0) > 0:
        return True
    return has_move_buff(player)
