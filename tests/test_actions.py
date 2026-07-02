import unittest

from lychee_basic_client.protocol.actions import action_message, claim_task, verify_gate


class ActionBuilderTests(unittest.TestCase):
    def test_action_message_wraps_action_list(self) -> None:
        self.assertEqual(
            {
                "msg_name": "action",
                "msg_data": {
                    "matchId": "match-1",
                    "round": 3,
                    "playerId": 1006,
                    "actions": [{"action": "CLAIM_TASK", "taskId": "T01_1"}],
                },
            },
            action_message("match-1", 3, 1006, [claim_task("T01_1")]),
        )

    def test_verify_gate_can_bind_rush_tactic(self) -> None:
        self.assertEqual(
            {"action": "VERIFY_GATE", "targetNodeId": "S14", "rushTactic": "BREAK_ORDER"},
            verify_gate("S14", "BREAK_ORDER"),
        )


if __name__ == "__main__":
    unittest.main()

