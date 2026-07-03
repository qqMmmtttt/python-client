import unittest

from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.combat import CombatStrategy
from lychee_basic_client.strategies.context import StrategyContext


class CombatStrategyTests(unittest.TestCase):
    def test_default_card_prefers_xian_gong(self) -> None:
        state = GameState.from_inquire(
            {
                "matchId": "match-1",
                "round": 12,
                "phase": "NORMAL",
                "players": [
                    {
                        "playerId": 1001,
                        "teamId": "RED",
                        "state": "CONTESTING",
                        "currentNodeId": "S07",
                        "guardActionPoint": 1,
                        "goodFruit": 100,
                        "freshness": 90,
                        "resources": {},
                    }
                ],
                "contests": [
                    {
                        "contestId": "contest-1",
                        "contestType": "TASK",
                        "redPlayerId": 1001,
                        "bluePlayerId": 2002,
                    }
                ],
                "events": [],
                "actionResults": [],
            },
            1001,
            GameState(match_id="match-1", round_no=1, player_id=1001).game_map,
        )

        self.assertEqual(
            [{"action": "WINDOW_CARD", "contestId": "contest-1", "card": "XIAN_GONG"}],
            CombatStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_counter_card_on_round_two(self) -> None:
        state = GameState.from_inquire(
            {
                "matchId": "match-1",
                "round": 14,
                "phase": "NORMAL",
                "players": [
                    {
                        "playerId": 1001,
                        "teamId": "RED",
                        "state": "CONTESTING",
                        "currentNodeId": "S07",
                        "guardActionPoint": 1,
                        "goodFruit": 100,
                        "freshness": 90,
                        "resources": {"PASS_TOKEN": 1, "FAST_HORSE": 1},
                    }
                ],
                "contests": [
                    {
                        "contestId": "contest-1",
                        "contestType": "TASK",
                        "redPlayerId": 1001,
                        "bluePlayerId": 2002,
                        "roundIndex": 2,
                        "cards": {"2002": "XIAN_GONG"},
                    }
                ],
                "events": [],
                "actionResults": [],
            },
            1001,
            GameState(match_id="match-1", round_no=1, player_id=1001).game_map,
        )

        self.assertEqual(
            [{"action": "WINDOW_CARD", "contestId": "contest-1", "card": "QIANG_XING"}],
            CombatStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_abstain_after_draw_limit_reached(self) -> None:
        strategy = CombatStrategy()
        base_player = {
            "playerId": 1001,
            "teamId": "RED",
            "state": "CONTESTING",
            "currentNodeId": "S02",
            "guardActionPoint": 1,
            "goodFruit": 100,
            "freshness": 90,
            "resources": {},
        }
        resolved_draws = [
            {
                "contestId": "draw-1",
                "contestType": "TASK",
                "targetNodeId": "S02",
                "redPlayerId": 1001,
                "bluePlayerId": 2002,
                "resolved": True,
                "winnerTeamId": "DRAW",
            },
            {
                "contestId": "draw-2",
                "contestType": "TASK",
                "targetNodeId": "S02",
                "redPlayerId": 1001,
                "bluePlayerId": 2002,
                "resolved": True,
                "winnerTeamId": "DRAW",
            },
        ]
        state = GameState.from_inquire(
            {
                "matchId": "match-1",
                "round": 30,
                "phase": "NORMAL",
                "players": [base_player],
                "contests": resolved_draws
                + [
                    {
                        "contestId": "contest-new",
                        "contestType": "TASK",
                        "targetNodeId": "S02",
                        "redPlayerId": 1001,
                        "bluePlayerId": 2002,
                        "roundIndex": 1,
                    }
                ],
                "events": [],
                "actionResults": [],
            },
            1001,
            GameState(match_id="match-1", round_no=1, player_id=1001).game_map,
        )

        self.assertEqual(
            [{"action": "WINDOW_CARD", "contestId": "contest-new", "card": "ABSTAIN"}],
            strategy.decide(StrategyContext.from_state(state)),
        )


if __name__ == "__main__":
    unittest.main()

