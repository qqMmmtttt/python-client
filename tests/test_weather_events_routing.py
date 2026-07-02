import unittest

from lychee_basic_client.config import Config
from lychee_basic_client.events.handlers import summarize_events
from lychee_basic_client.models.state import GameState
from lychee_basic_client.models.weather import WeatherState
from lychee_basic_client.strategies.routing import RoutePolicy


class WeatherEventsRoutingTests(unittest.TestCase):
    def test_weather_route_multiplier_reads_active_events(self) -> None:
        weather = WeatherState.from_raw({"active": [{"type": "HEAVY_RAIN"}]})

        self.assertEqual(1.35, weather.route_multiplier("WATER"))
        self.assertEqual(1.0, weather.route_multiplier("ROAD"))

    def test_event_summary_extracts_player_scoped_results(self) -> None:
        summary = summarize_events(
            [
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {"playerId": 1001, "targetNodeId": "S02"},
                },
                {
                    "type": "ACTION_REJECTED",
                    "payload": {"playerId": 1001, "action": "MOVE", "errorCode": "BLOCKED"},
                },
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {"playerId": 2002, "targetNodeId": "S99"},
                },
            ],
            1001,
        )

        self.assertEqual({"S02"}, summary.completed_process_nodes)
        self.assertEqual("MOVE", summary.rejected_actions[0].action)

    def test_task_process_complete_does_not_mark_station_process_done(self) -> None:
        summary = summarize_events(
            [
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {
                        "playerId": 1001,
                        "targetNodeId": "S02",
                        "action": "CLAIM_TASK",
                        "taskId": "task-t02",
                    },
                }
            ],
            1001,
        )

        self.assertEqual(set(), summary.completed_process_nodes)

    def test_generic_route_policy_ignores_first_round_profile(self) -> None:
        state = _final_like_state()
        policy = RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1", route_profile="generic"))

        self.assertEqual("B", policy.next_hop(state, "A", "G"))

    def test_auto_route_policy_falls_back_for_unknown_maps(self) -> None:
        state = _final_like_state()
        policy = RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1", route_profile="auto"))

        self.assertEqual("B", policy.next_hop(state, "A", "G"))


def _final_like_state() -> GameState:
    return GameState.from_start(
        {
            "matchId": "match-final-map",
            "round": 1,
            "nodes": [
                {"nodeId": "A", "type": "START"},
                {"nodeId": "B"},
                {"nodeId": "G", "type": "GATE"},
                {"nodeId": "T", "type": "FINISH"},
            ],
            "edges": [
                {"fromNodeId": "A", "toNodeId": "B", "routeType": "ROAD", "distance": 1},
                {"fromNodeId": "B", "toNodeId": "G", "routeType": "ROAD", "distance": 1},
                {"fromNodeId": "G", "toNodeId": "T", "routeType": "ROAD", "distance": 1},
            ],
            "players": [
                {"playerId": 1001, "teamId": "RED", "state": "IDLE", "currentNodeId": "A"}
            ],
        },
        1001,
    )


if __name__ == "__main__":
    unittest.main()
