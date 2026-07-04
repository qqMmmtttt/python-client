import tempfile
import unittest
from pathlib import Path

from lychee_basic_client.models.state import GameState
from lychee_basic_client.public_info import PublicInformationManager, PublicStateRecorder
from lychee_basic_client.testing.fixtures import sample_inquire, sample_start


class PublicInformationTests(unittest.TestCase):
    def test_manager_builds_structured_public_snapshot(self) -> None:
        start_state = GameState.from_start(sample_start(), 1006)
        state = GameState.from_inquire(
            _rich_inquire(round_no=9),
            1006,
            start_state.game_map,
        )
        manager = PublicInformationManager()

        snapshot = manager.update(state)

        self.assertEqual(snapshot, manager.latest)
        self.assertEqual(1, len(manager.history))
        self.assertEqual(2, len(snapshot.players))
        self.assertEqual([2001], [player.player_id for player in snapshot.opponents()])
        self.assertEqual(["T_001"], [task.task_id for task in snapshot.active_tasks()])
        self.assertEqual("S02", snapshot.nodes[0].node_id)
        self.assertEqual("HEAVY_RAIN", snapshot.weather.active[0]["type"])

    def test_recorder_writes_chinese_round_file_without_raw_json(self) -> None:
        start_state = GameState.from_start(sample_start(), 1006)
        state = GameState.from_inquire(
            _rich_inquire(round_no=9),
            1006,
            start_state.game_map,
        )
        snapshot = PublicInformationManager().update(state)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = PublicStateRecorder(tmp_dir).record(snapshot)
            text = path.read_text(encoding="utf-8")

        self.assertEqual(Path(tmp_dir) / "public_state" / "round_0009.txt", path)
        self.assertIn("第 0009 轮公开状态档案", text)
        self.assertIn("二、玩家信息", text)
        self.assertIn("玩家 2001（对手）", text)
        self.assertIn("currentNodeId（停靠时为所在节点；移动中为路线起点）", text)
        self.assertIn("四、任务信息", text)
        self.assertIn("五、天气信息", text)
        self.assertIn("七、事件信息", text)
        self.assertNotIn("{", text)
        self.assertNotIn("}", text)

    def test_start_snapshot_uses_start_suffix(self) -> None:
        state = GameState.from_start(sample_start(), 1006)
        snapshot = PublicInformationManager().update(state)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = PublicStateRecorder(tmp_dir).record(snapshot, source="start")

        self.assertEqual(Path(tmp_dir) / "public_state" / "round_0001_start.txt", path)


def _rich_inquire(round_no: int) -> dict:
    data = sample_inquire(round_no=round_no)
    data["players"] = [
        {
            "playerId": 1006,
            "teamId": "RED",
            "state": "MOVING",
            "currentNodeId": "S01",
            "nextNodeId": "S02",
            "routeEdgeId": "E01",
            "moveDirection": "FORWARD",
            "edgeProgressMs": 2000,
            "edgeTotalMs": 10000,
            "verified": False,
            "delivered": False,
            "freshness": 96.5,
            "goodFruit": 99,
            "badFruit": 1,
            "guardActionPoint": 2,
            "rushTacticUsedCount": 0,
            "breakOrderReady": True,
            "squadAvailable": 6,
            "squadInFlight": 2,
            "taskScore": 30,
            "totalScore": 30,
            "resources": {"FAST_HORSE": 1, "ICE_BOX": 1},
            "buffs": [{"type": "FAST_HORSE"}],
        },
        {
            "playerId": 2001,
            "teamId": "BLUE",
            "state": "IDLE",
            "currentNodeId": "S02",
            "verified": False,
            "delivered": False,
            "freshness": 94,
            "goodFruit": 98,
            "badFruit": 2,
            "squadAvailable": 4,
            "taskScore": 0,
            "totalScore": 0,
            "resources": {},
        },
    ]
    data["nodes"] = [
        {
            "nodeId": "S02",
            "nodeName": "南岭驿",
            "nodeType": "STATION",
            "hasObstacle": True,
            "obstacleType": "FLOOD",
            "resourceStock": {"FAST_HORSE": 1},
            "guard": {"ownerTeamId": "BLUE", "defense": 4, "active": True},
            "scouts": [{"playerId": 1006, "remainRound": 12}],
        }
    ]
    data["tasks"] = [
        {
            "taskId": "T_001",
            "taskTemplateId": "T02",
            "nodeId": "S02",
            "score": 30,
            "processRound": 3,
            "ownerPlayerId": 0,
            "protectionPlayerId": 0,
            "expireRound": 120,
            "active": True,
            "completed": False,
            "failed": False,
        }
    ]
    data["weather"] = {
        "active": [{"weatherId": "W1", "type": "HEAVY_RAIN", "region": "WATER", "remainRound": 5}],
        "forecast": [{"weatherId": "W2", "type": "HOT", "region": "ROAD", "startRound": 20, "durationRound": 8}],
    }
    data["contests"] = [
        {
            "contestId": "C_001",
            "targetNodeId": "S02",
            "status": "RUNNING",
            "resolved": False,
            "redPlayerId": 1006,
            "bluePlayerId": 2001,
        }
    ]
    data["events"] = [
        {
            "type": "SQUAD_WEAKEN",
            "payload": {
                "playerId": 1006,
                "targetNodeId": "S02",
                "action": "SQUAD_WEAKEN",
                "message": "accepted",
            },
        }
    ]
    data["actionResults"] = [
        {
            "playerId": 1006,
            "action": "MOVE",
            "accepted": False,
            "result": "REJECTED",
            "errorCode": "GUARD_BLOCKED",
            "targetNodeId": "S02",
        }
    ]
    return data


if __name__ == "__main__":
    unittest.main()
