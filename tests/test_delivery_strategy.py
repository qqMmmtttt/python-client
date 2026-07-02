import json
import unittest
from pathlib import Path
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.delivery import DeliveryStrategy
from lychee_basic_client.strategies.routing import RoutePolicy


def _state(
    node_id: str,
    *,
    phase: str = "NORMAL",
    verified: bool = False,
    events: Optional[list[dict[str, Any]]] = None,
) -> GameState:
    map_config = json.loads(Path("example_data/map_config.json").read_text(encoding="utf-8"))
    state = GameState.from_start(
        {
            "matchId": "match-real-map",
            "round": 1,
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
                    "goodFruit": 100,
                    "freshness": 90,
                }
            ],
            "events": events or [],
        },
        1001,
    )
    state.events = events or []
    return state


class DeliveryStrategyTests(unittest.TestCase):
    def _strategy(self, route_profile: str = "auto") -> DeliveryStrategy:
        config = Config("127.0.0.1", 30000, 1001, "red", "0.1", route_profile=route_profile)
        return DeliveryStrategy(RoutePolicy(config))

    def test_real_map_uses_safe_preferred_first_hop(self) -> None:
        strategy = self._strategy()
        state = _state("S01")
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S02"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_processes_required_station_once(self) -> None:
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
            [{"action": "MOVE", "targetNodeId": "S03"}],
            strategy.decide(StrategyContext.from_state(completed)),
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

    def test_delivers_at_terminal_after_verification(self) -> None:
        strategy = self._strategy()
        state = _state("S15", phase="RUSH", verified=True)
        strategy.on_start(state)

        self.assertEqual([{"action": "DELIVER"}], strategy.decide(StrategyContext.from_state(state)))


if __name__ == "__main__":
    unittest.main()
