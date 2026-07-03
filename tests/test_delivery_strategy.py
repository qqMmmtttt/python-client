import json
import unittest
from pathlib import Path
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState, NodeState
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.delivery import DeliveryStrategy
from lychee_basic_client.strategies.routing import RoutePolicy


def _state(
    node_id: str,
    *,
    round_no: int = 1,
    phase: str = "NORMAL",
    verified: bool = False,
    good_fruit: int = 100,
    bad_fruit: int = 0,
    freshness: float = 90,
    break_order_ready: bool = False,
    tasks: Optional[list[dict[str, Any]]] = None,
    nodes: Optional[list[dict[str, Any]]] = None,
    events: Optional[list[dict[str, Any]]] = None,
) -> GameState:
    map_config = json.loads(Path("example_data/map_config.json").read_text(encoding="utf-8"))
    state = GameState.from_start(
        {
            "matchId": "match-real-map",
            "round": round_no,
            "phase": phase,
            "nodes": map_config["nodes"],
            "edges": map_config["edges"],
            "processNodes": map_config["processNodes"],
            "players": [
                {
                    "playerId": 1001,
                    "teamId": "RED",
                    "state": "IDLE",
                    "currentNodeId": node_id,
                    "verified": verified,
                    "goodFruit": good_fruit,
                    "badFruit": bad_fruit,
                    "freshness": freshness,
                    "breakOrderReady": break_order_ready,
                }
            ],
            "tasks": tasks or [],
            "nodes": map_config["nodes"],
            "events": events or [],
        },
        1001,
    )
    state.events = events or []
    if nodes is not None:
        state.nodes = {
            node["nodeId"]: NodeState.from_raw(node)
            for node in nodes
            if node.get("nodeId")
        }
    state.tasks = tasks or []
    return state


class DeliveryStrategyTests(unittest.TestCase):
    def _strategy(self, route_profile: str = "auto") -> DeliveryStrategy:
        config = Config("127.0.0.1", 30000, 1001, "red", "0.1", route_profile=route_profile)
        return DeliveryStrategy(RoutePolicy(config))

    def test_real_map_goes_to_initial_transfer_first(self) -> None:
        strategy = self._strategy()
        state = _state("S01")
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S02"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_processes_required_station_once_then_can_follow_dynamic_route(self) -> None:
        strategy = self._strategy()
        state = _state("S02")
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "PROCESS", "targetNodeId": "S02"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

        completed = _state(
            "S02",
            events=[
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {"playerId": 1001, "targetNodeId": "S02"},
                }
            ],
        )
        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S04"}],
            strategy.decide(StrategyContext.from_state(completed)),
        )

    def test_auto_route_can_take_safe_land_task_after_s02(self) -> None:
        strategy = self._strategy()
        state = _state("S02")
        strategy.on_start(state)
        strategy.decide(StrategyContext.from_state(state))

        completed = _state(
            "S02",
            tasks=[
                {
                    "taskId": "task-s03",
                    "taskTemplateId": "T01",
                    "nodeId": "S03",
                    "score": 30,
                    "active": True,
                    "processRound": 3,
                }
            ],
            events=[
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {"playerId": 1001, "targetNodeId": "S02"},
                }
            ],
        )

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S03"}],
            strategy.decide(StrategyContext.from_state(completed)),
        )

    def test_explicit_water_profile_is_not_diverted_to_land_task_after_s02(self) -> None:
        strategy = self._strategy(route_profile="first-round-water")
        state = _state("S02")
        strategy.on_start(state)
        strategy.decide(StrategyContext.from_state(state))

        completed = _state(
            "S02",
            tasks=[
                {
                    "taskId": "task-s03",
                    "taskTemplateId": "T01",
                    "nodeId": "S03",
                    "score": 30,
                    "active": True,
                    "processRound": 3,
                }
            ],
            events=[
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {"playerId": 1001, "targetNodeId": "S02"},
                }
            ],
        )

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S04"}],
            strategy.decide(StrategyContext.from_state(completed)),
        )

    def test_auto_route_can_leave_dock_for_safe_land_task(self) -> None:
        strategy = self._strategy()
        state = _state("S04")
        strategy.on_start(state)
        strategy.decide(StrategyContext.from_state(state))

        completed = _state(
            "S04",
            tasks=[
                {
                    "taskId": "task-s07",
                    "taskTemplateId": "T02",
                    "nodeId": "S07",
                    "score": 30,
                    "active": True,
                    "processRound": 4,
                }
            ],
            events=[
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {"playerId": 1001, "targetNodeId": "S04"},
                }
            ],
        )

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S07"}],
            strategy.decide(StrategyContext.from_state(completed)),
        )

    def test_explicit_water_profile_continues_from_dock_to_water_station(self) -> None:
        strategy = self._strategy(route_profile="first-round-water")
        state = _state("S04")
        strategy.on_start(state)
        strategy.decide(StrategyContext.from_state(state))

        completed = _state(
            "S04",
            tasks=[
                {
                    "taskId": "task-s07",
                    "taskTemplateId": "T02",
                    "nodeId": "S07",
                    "score": 30,
                    "active": True,
                    "processRound": 4,
                }
            ],
            events=[
                {
                    "type": "PROCESS_COMPLETE",
                    "payload": {"playerId": 1001, "targetNodeId": "S04"},
                }
            ],
        )

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S05"}],
            strategy.decide(StrategyContext.from_state(completed)),
        )

    def test_board_station_uses_process_action(self) -> None:
        strategy = self._strategy()
        state = _state("S04")
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "PROCESS", "targetNodeId": "S04"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_reprocesses_fixed_station_after_revisiting(self) -> None:
        strategy = self._strategy()
        strategy.on_start(_state("S02"))

        self.assertEqual(
            [{"action": "PROCESS", "targetNodeId": "S02"}],
            strategy.decide(StrategyContext.from_state(_state("S02"))),
        )
        strategy.decide(
            StrategyContext.from_state(
                _state(
                    "S02",
                    events=[
                        {
                            "type": "PROCESS_COMPLETE",
                            "payload": {"playerId": 1001, "targetNodeId": "S02"},
                        }
                    ],
                )
            )
        )
        strategy.decide(StrategyContext.from_state(_state("S03")))

        self.assertEqual(
            [{"action": "PROCESS", "targetNodeId": "S02"}],
            strategy.decide(StrategyContext.from_state(_state("S02"))),
        )

    def test_unverified_terminal_returns_to_gate(self) -> None:
        strategy = self._strategy()
        state = _state("S15", phase="RUSH", verified=False)
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S14"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_waits_for_rush_before_gate_verification(self) -> None:
        strategy = self._strategy()
        state = _state("S14")
        strategy.on_start(state)

        self.assertEqual([], strategy.decide(StrategyContext.from_state(state)))

    def test_verifies_gate_in_rush_phase(self) -> None:
        strategy = self._strategy()
        state = _state("S14", phase="RUSH")
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "VERIFY_GATE", "targetNodeId": "S14"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_gate_verification_does_not_bind_break_order_before_ready(self) -> None:
        strategy = self._strategy()
        state = _state("S14", round_no=565, phase="RUSH", bad_fruit=2)
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "VERIFY_GATE", "targetNodeId": "S14"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_late_gate_verification_binds_break_order_when_ready_and_affordable(self) -> None:
        strategy = self._strategy()
        state = _state("S14", round_no=565, phase="RUSH", bad_fruit=2, break_order_ready=True)
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "VERIFY_GATE", "targetNodeId": "S14", "rushTactic": "BREAK_ORDER"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivers_at_terminal_after_verification(self) -> None:
        strategy = self._strategy()
        state = _state("S15", phase="RUSH", verified=True)
        strategy.on_start(state)

        self.assertEqual([{"action": "DELIVER"}], strategy.decide(StrategyContext.from_state(state)))


if __name__ == "__main__":
    unittest.main()
