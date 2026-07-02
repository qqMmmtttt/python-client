import json
import unittest
from pathlib import Path
from typing import Any, Optional

from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.resources import ResourceStrategy
from lychee_basic_client.strategies.squad import SquadStrategy


def _state(
    node_id: str,
    *,
    round_no: int = 1,
    phase: str = "NORMAL",
    resources: Optional[dict[str, int]] = None,
    squad_available: int = 8,
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
                    "verified": False,
                    "goodFruit": 100,
                    "freshness": 90,
                    "resources": resources or {},
                    "squadAvailable": squad_available,
                }
            ],
            "weather": {},
        },
        1001,
    )
    state = GameState.from_inquire(
        {
            "matchId": "match-real-map",
            "round": round_no,
            "phase": phase,
            "players": [
                {
                    "playerId": 1001,
                    "teamId": "RED",
                    "state": "IDLE",
                    "currentNodeId": node_id,
                    "verified": False,
                    "goodFruit": 100,
                    "freshness": 90,
                    "resources": resources or {},
                    "squadAvailable": squad_available,
                }
            ],
            "nodes": nodes or [],
            "tasks": [],
            "events": events or [],
            "contests": [],
            "actionResults": [],
        },
        1001,
        state.game_map,
    )
    return state


class OptimizationStrategyTests(unittest.TestCase):
    def test_resource_strategy_uses_intel_on_current_process_node(self) -> None:
        state = _state("S13", round_no=450, resources={"INTEL": 1})

        self.assertEqual(
            [{"action": "USE_RESOURCE", "resourceType": "INTEL", "targetNodeId": "S13"}],
            ResourceStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_resource_strategy_can_claim_intel(self) -> None:
        state = _state("S10", nodes=[{"nodeId": "S10", "resourceStock": {"INTEL": 1}}])

        self.assertEqual(
            [{"action": "CLAIM_RESOURCE", "targetNodeId": "S10", "resourceType": "INTEL"}],
            ResourceStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_squad_strategy_scouts_process_nodes_early(self) -> None:
        strategy = SquadStrategy()
        state = _state("S01")
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SQUAD_SCOUT", "targetNodeId": "S04"}],
            strategy.decide(StrategyContext.from_state(state)),
        )
        self.assertEqual(
            [{"action": "SQUAD_SCOUT", "targetNodeId": "S05"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_squad_strategy_clears_future_obstacle_before_scouting(self) -> None:
        strategy = SquadStrategy()
        state = _state(
            "S09",
            nodes=[{"nodeId": "S10", "hasObstacle": True, "resourceStock": {}}],
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SQUAD_CLEAR", "targetNodeId": "S10"}],
            strategy.decide(StrategyContext.from_state(state)),
        )


if __name__ == "__main__":
    unittest.main()
