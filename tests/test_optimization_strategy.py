import json
import unittest
from pathlib import Path
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.factory import build_strategy
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.resources import ResourceStrategy
from lychee_basic_client.strategies.squad import SquadStrategy


def _state(
    node_id: str,
    *,
    round_no: int = 1,
    phase: str = "NORMAL",
    player_state: str = "IDLE",
    next_node_id: Optional[str] = None,
    verified: bool = False,
    task_score: int = 0,
    total_score: int = 0,
    good_fruit: int = 100,
    freshness: float = 90,
    resources: Optional[dict[str, int]] = None,
    squad_available: int = 8,
    nodes: Optional[list[dict[str, Any]]] = None,
    events: Optional[list[dict[str, Any]]] = None,
    weather: Optional[dict[str, Any]] = None,
    extra_players: Optional[list[dict[str, Any]]] = None,
) -> GameState:
    map_config = json.loads(Path("example_data/map_config.json").read_text(encoding="utf-8"))
    player = {
        "playerId": 1001,
        "teamId": "RED",
        "state": player_state,
        "currentNodeId": node_id,
        "nextNodeId": next_node_id,
        "verified": verified,
        "goodFruit": good_fruit,
        "freshness": freshness,
        "resources": resources or {},
        "squadAvailable": squad_available,
        "taskScore": task_score,
        "totalScore": total_score,
        "buffs": [],
    }
    players = [player, *(extra_players or [])]
    state = GameState.from_start(
        {
            "matchId": "match-real-map",
            "round": round_no,
            "phase": phase,
            "nodes": map_config["nodes"],
            "edges": map_config["edges"],
            "processNodes": map_config["processNodes"],
            "players": players,
            "weather": weather or {},
        },
        1001,
    )
    state = GameState.from_inquire(
        {
            "matchId": "match-real-map",
            "round": round_no,
            "phase": phase,
            "players": players,
            "nodes": nodes or [],
            "tasks": [],
            "events": events or [],
            "weather": weather or {},
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

    def test_resource_strategy_uses_route_distance_for_intel_range(self) -> None:
        state = _state("S12", round_no=450, resources={"INTEL": 1})

        self.assertEqual([], ResourceStrategy().decide(StrategyContext.from_state(state)))

    def test_pipeline_uses_intel_before_fixed_process(self) -> None:
        state = _state("S13", round_no=450, resources={"INTEL": 1})
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [
                {"action": "USE_RESOURCE", "resourceType": "INTEL", "targetNodeId": "S13"},
                {"action": "SQUAD_SCOUT", "targetNodeId": "S04"},
            ],
            strategy.decide(state),
        )

    def test_resource_strategy_can_claim_intel(self) -> None:
        state = _state("S10", nodes=[{"nodeId": "S10", "resourceStock": {"INTEL": 1}}])

        self.assertEqual(
            [{"action": "CLAIM_RESOURCE", "targetNodeId": "S10", "resourceType": "INTEL"}],
            ResourceStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_squad_strategy_reserves_initial_team_for_key_pass_guards(self) -> None:
        strategy = SquadStrategy()
        state = _state("S01")
        strategy.on_start(state)

        self.assertEqual([], strategy.decide(StrategyContext.from_state(state)))

    def test_squad_strategy_scouts_when_guard_reserve_is_extra_safe(self) -> None:
        strategy = SquadStrategy()
        state = _state("S01", squad_available=9)
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SQUAD_SCOUT", "targetNodeId": "S04"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_squad_strategy_preserves_guard_reserve_before_clearing_obstacle(self) -> None:
        strategy = SquadStrategy()
        state = _state(
            "S09",
            nodes=[{"nodeId": "S10", "hasObstacle": True, "resourceStock": {}}],
        )
        strategy.on_start(state)

        self.assertEqual([], strategy.decide(StrategyContext.from_state(state)))

    def test_squad_strategy_weakens_route_edge_enemy_guard_before_scouting(self) -> None:
        strategy = SquadStrategy()
        state = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 4, "active": True},
                }
            ],
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SQUAD_WEAKEN", "targetNodeId": "S10"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_squad_strategy_can_repeat_weaken_until_route_edge_guard_is_expected_clear(self) -> None:
        strategy = SquadStrategy()
        state = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 7, "active": True},
                }
            ],
        )
        strategy.on_start(state)
        context = StrategyContext.from_state(state)

        for _ in range(4):
            self.assertEqual(
                [{"action": "SQUAD_WEAKEN", "targetNodeId": "S10"}],
                strategy.decide(context),
            )
        self.assertEqual([], strategy.decide(context))

    def test_pipeline_weakens_next_node_guard_while_detouring_route_edge(self) -> None:
        state = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 7, "active": True},
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [
                {"action": "MOVE", "targetNodeId": "S07"},
                {"action": "SQUAD_WEAKEN", "targetNodeId": "S10"},
            ],
            strategy.decide(state),
        )

    def test_pipeline_does_not_let_intel_preempt_delivery_move(self) -> None:
        state = _state(
            "S09",
            round_no=250,
            resources={"INTEL": 1},
            squad_available=0,
            nodes=[
                {"nodeId": "S08", "hasObstacle": True, "obstacleType": "FLOOD", "resourceStock": {}},
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S10"}],
            strategy.decide(state),
        )

    def test_pipeline_does_not_let_intel_preempt_next_hop_clear(self) -> None:
        state = _state(
            "S09",
            round_no=250,
            resources={"INTEL": 1},
            squad_available=0,
            nodes=[
                {"nodeId": "S10", "hasObstacle": True, "obstacleType": "FLOOD", "resourceStock": {}},
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "CLEAR", "targetNodeId": "S10"}],
            strategy.decide(state),
        )

    def test_pipeline_claims_high_value_resource_before_plain_move(self) -> None:
        state = _state(
            "S09",
            round_no=250,
            squad_available=0,
            nodes=[
                {"nodeId": "S09", "hasObstacle": False, "resourceStock": {"FAST_HORSE": 1}},
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "CLAIM_RESOURCE", "targetNodeId": "S09", "resourceType": "FAST_HORSE"}],
            strategy.decide(state),
        )

    def test_pipeline_keeps_blocking_clear_ahead_of_resource_claim(self) -> None:
        state = _state(
            "S09",
            round_no=250,
            squad_available=0,
            nodes=[
                {"nodeId": "S09", "hasObstacle": False, "resourceStock": {"FAST_HORSE": 1}},
                {"nodeId": "S10", "hasObstacle": True, "obstacleType": "FLOOD", "resourceStock": {}},
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "CLEAR", "targetNodeId": "S10"}],
            strategy.decide(state),
        )

    def test_pipeline_sets_key_guard_after_task_threshold(self) -> None:
        state = _state(
            "S10",
            round_no=260,
            task_score=90,
            squad_available=0,
            nodes=[{"nodeId": "S10", "hasObstacle": False, "resourceStock": {}}],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "IDLE",
                    "currentNodeId": "S09",
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SET_GUARD", "targetNodeId": "S10", "extraGoodFruit": 0}],
            strategy.decide(state),
        )

    def test_pipeline_can_guard_gate_when_opponent_still_needs_it(self) -> None:
        state = _state(
            "S14",
            round_no=390,
            task_score=90,
            squad_available=0,
            nodes=[{"nodeId": "S14", "hasObstacle": False, "resourceStock": {}}],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "IDLE",
                    "currentNodeId": "S11",
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SET_GUARD", "targetNodeId": "S14", "extraGoodFruit": 0}],
            strategy.decide(state),
        )

    def test_pipeline_does_not_guard_node_outside_opponent_route(self) -> None:
        state = _state(
            "S07",
            round_no=260,
            task_score=90,
            squad_available=0,
            nodes=[{"nodeId": "S07", "hasObstacle": False, "resourceStock": {}}],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "IDLE",
                    "currentNodeId": "S09",
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertNotEqual(
            [{"action": "SET_GUARD", "targetNodeId": "S07", "extraGoodFruit": 0}],
            strategy.decide(state),
        )

    def test_pipeline_avoids_guard_when_far_ahead_on_score(self) -> None:
        state = _state(
            "S10",
            round_no=260,
            task_score=90,
            total_score=180,
            squad_available=0,
            nodes=[{"nodeId": "S10", "hasObstacle": False, "resourceStock": {}}],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "IDLE",
                    "currentNodeId": "S09",
                    "totalScore": 100,
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S11"}],
            strategy.decide(state),
        )

    def test_pipeline_waits_to_guard_until_task_threshold(self) -> None:
        state = _state(
            "S10",
            round_no=260,
            task_score=60,
            squad_available=0,
            nodes=[{"nodeId": "S10", "hasObstacle": False, "resourceStock": {}}],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "IDLE",
                    "currentNodeId": "S09",
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S11"}],
            strategy.decide(state),
        )

    def test_pipeline_uses_rush_protect_when_freshness_is_dangerous(self) -> None:
        state = _state(
            "S12",
            round_no=460,
            phase="RUSH",
            freshness=40,
            squad_available=0,
            nodes=[{"nodeId": "S12", "hasObstacle": False, "resourceStock": {}}],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "RUSH_PROTECT"}],
            strategy.decide(state),
        )


if __name__ == "__main__":
    unittest.main()
