import json
import logging
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState
from lychee_basic_client.observability.logging_setup import setup_logging
from lychee_basic_client.strategies.factory import build_strategy
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.resources import ResourceStrategy
from lychee_basic_client.strategies.routing import RoutePolicy
from lychee_basic_client.strategies.squad import SquadStrategy


def _close_package_handlers() -> None:
    logger = logging.getLogger("lychee_basic_client")
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
    logger.handlers.clear()


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
    tasks: Optional[list[dict[str, Any]]] = None,
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
            "tasks": tasks or [],
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

    def test_resource_strategy_does_not_use_horse_while_route_edge_guard_is_adjacent(self) -> None:
        state = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S07",
            resources={"FAST_HORSE": 1},
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )

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

    def test_speed_priority_claims_short_horse_on_water_route(self) -> None:
        state = _state(
            "S04",
            nodes=[{"nodeId": "S04", "resourceStock": {"SHORT_HORSE": 1}}],
        )
        strategy = ResourceStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )

        self.assertEqual(
            [{"action": "CLAIM_RESOURCE", "targetNodeId": "S04", "resourceType": "SHORT_HORSE"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_speed_priority_skips_boat_right_before_wuguan(self) -> None:
        state = _state(
            "S04",
            nodes=[{"nodeId": "S04", "resourceStock": {"BOAT_RIGHT": 1}}],
        )
        strategy = ResourceStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )

        self.assertEqual([], strategy.decide(StrategyContext.from_state(state)))

    def test_speed_priority_uses_horse_even_when_t06_exists(self) -> None:
        state = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            resources={"FAST_HORSE": 1},
            tasks=[
                {
                    "taskId": "task-t06",
                    "taskTemplateId": "T06",
                    "nodeId": "S09",
                    "score": 30,
                    "active": True,
                }
            ],
            nodes=[{"nodeId": "S10", "resourceStock": {}}],
        )
        strategy = ResourceStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )

        self.assertEqual(
            [{"action": "USE_RESOURCE", "resourceType": "FAST_HORSE"}],
            strategy.decide(StrategyContext.from_state(state)),
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

    def test_speed_priority_squad_scouts_while_preserving_guard_reserve(self) -> None:
        strategy = SquadStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        state = _state("S01", squad_available=8)
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SQUAD_SCOUT", "targetNodeId": "S04"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

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

    def test_squad_strategy_keeps_weakening_adjacent_guard_after_route_edge_pivot(self) -> None:
        strategy = SquadStrategy()
        blocked = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            squad_available=8,
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )
        strategy.on_start(blocked)

        self.assertEqual(
            [{"action": "SQUAD_WEAKEN", "targetNodeId": "S10"}],
            strategy.decide(StrategyContext.from_state(blocked)),
        )

        pivot_edge = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S07",
            squad_available=6,
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )

        self.assertEqual(
            [{"action": "SQUAD_WEAKEN", "targetNodeId": "S10"}],
            strategy.decide(StrategyContext.from_state(pivot_edge)),
        )

    def test_pipeline_weakens_next_node_guard_while_holding_route_edge(self) -> None:
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
                {"action": "WAIT"},
                {"action": "SQUAD_WEAKEN", "targetNodeId": "S10"},
            ],
            strategy.decide(state),
        )

    def test_pipeline_holds_wrong_pivot_edge_while_squad_weakens_observed_guard(self) -> None:
        state = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)
        strategy.decide(state)

        pivot_edge = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S07",
            resources={"FAST_HORSE": 1},
            squad_available=6,
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )

        self.assertEqual(
            [
                {"action": "MOVE", "targetNodeId": "S07"},
                {"action": "SQUAD_WEAKEN", "targetNodeId": "S10"},
            ],
            strategy.decide(pivot_edge),
        )

    def test_pipeline_holds_after_legacy_route_edge_pivot(self) -> None:
        state = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)
        strategy.decide(state)

        pivot_edge = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S08",
            resources={"FAST_HORSE": 1},
            squad_available=6,
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )

        self.assertEqual(
            [
                {"action": "MOVE", "targetNodeId": "S08"},
                {"action": "SQUAD_WEAKEN", "targetNodeId": "S10"},
            ],
            strategy.decide(pivot_edge),
        )

    def test_pipeline_can_break_guard_if_server_reports_origin_idle(self) -> None:
        guard_node = {
            "nodeId": "S10",
            "hasObstacle": False,
            "resourceStock": {},
            "guard": {"ownerTeamId": "BLUE", "defense": 4, "active": True},
        }
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        blocked_edge = _state(
            "S09",
            round_no=296,
            player_state="MOVING",
            next_node_id="S10",
            resources={"FAST_HORSE": 1},
            squad_available=6,
            nodes=[guard_node],
        )
        strategy.on_start(blocked_edge)

        self.assertEqual(
            [
                {"action": "WAIT"},
                {"action": "SQUAD_WEAKEN", "targetNodeId": "S10"},
            ],
            strategy.decide(blocked_edge),
        )

        origin_idle = _state(
            "S09",
            round_no=298,
            player_state="IDLE",
            squad_available=0,
            nodes=[guard_node],
        )
        self.assertEqual(
            [{"action": "BREAK_GUARD", "targetNodeId": "S10", "goodFruit": 2, "badFruit": 0}],
            strategy.decide(origin_idle),
        )

    def test_pipeline_inferrs_visible_guard_and_does_not_continue_to_stale_s07_pivot(self) -> None:
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        stale_pivot_edge = _state(
            "S09",
            round_no=301,
            player_state="MOVING",
            next_node_id="S07",
            resources={"FAST_HORSE": 1},
            squad_available=6,
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 6, "active": True},
                }
            ],
        )
        strategy.on_start(stale_pivot_edge)

        self.assertEqual(
            [
                {"action": "MOVE", "targetNodeId": "S07"},
                {"action": "SQUAD_WEAKEN", "targetNodeId": "S10"},
            ],
            strategy.decide(stale_pivot_edge),
        )

    def test_guard_log_records_route_edge_squad_hold_end_to_end_in_chinese(self) -> None:
        guard_node = {
            "nodeId": "S10",
            "hasObstacle": False,
            "resourceStock": {},
            "guard": {"ownerTeamId": "BLUE", "defense": 4, "active": True},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            setup_logging(tmp_dir, "ERROR")
            strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
            blocked_edge = _state(
                "S09",
                round_no=296,
                player_state="MOVING",
                next_node_id="S10",
                squad_available=6,
                nodes=[guard_node],
            )
            strategy.on_start(blocked_edge)
            strategy.decide(blocked_edge)
            strategy.decide(
                _state(
                    "S09",
                    round_no=297,
                    player_state="MOVING",
                    next_node_id="S08",
                    squad_available=6,
                    nodes=[guard_node],
                )
            )
            strategy.decide(
                _state(
                    "S09",
                    round_no=298,
                    player_state="IDLE",
                    squad_available=0,
                    nodes=[guard_node],
                )
            )
            _close_package_handlers()

            guard_log = (Path(tmp_dir) / "guard.log").read_text(encoding="utf-8")
            self.assertIn("【设卡处理｜途中小分队削弱】", guard_log)
            self.assertIn("【设卡处理｜节点态直接攻坚】", guard_log)
            self.assertIn("主车队提交 WAIT 悬停", guard_log)
            self.assertIn("本策略不再使用换道复位", guard_log)
            self.assertNotIn("【设卡处理｜启动换道复位】", guard_log)
            self.assertNotIn("每帧决策摘要", guard_log)

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
            [{"action": "SET_GUARD", "targetNodeId": "S10", "extraGoodFruit": 2}],
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
            [{"action": "SET_GUARD", "targetNodeId": "S14", "extraGoodFruit": 1}],
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

    def test_speed_priority_sets_wuguan_guard_even_when_far_ahead_on_score(self) -> None:
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
            [{"action": "SET_GUARD", "targetNodeId": "S10", "extraGoodFruit": 2}],
            strategy.decide(state),
        )

    def test_speed_priority_sets_wuguan_guard_before_task_threshold(self) -> None:
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
            [{"action": "SET_GUARD", "targetNodeId": "S10", "extraGoodFruit": 2}],
            strategy.decide(state),
        )

    def test_wuguan_trap_sets_luoyang_guard_before_resource_pickup(self) -> None:
        state = _state(
            "S09",
            round_no=230,
            task_score=60,
            squad_available=0,
            nodes=[
                {"nodeId": "S09", "hasObstacle": False, "resourceStock": {"FAST_HORSE": 1}},
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "IDLE",
                    "currentNodeId": "S05",
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SET_GUARD", "targetNodeId": "S09", "extraGoodFruit": 2}],
            strategy.decide(state),
        )

    def test_wuguan_trap_waits_at_wuguan_after_luoyang_guard(self) -> None:
        state = _state(
            "S10",
            round_no=280,
            task_score=60,
            squad_available=0,
            nodes=[
                {
                    "nodeId": "S09",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "RED", "defense": 6, "active": True},
                },
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "IDLE",
                    "currentNodeId": "S09",
                    "nextNodeId": None,
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual([{"action": "WAIT"}], strategy.decide(state))

    def test_wuguan_trap_keeps_waiting_when_server_reports_node_waiting(self) -> None:
        state = _state(
            "S10",
            round_no=351,
            player_state="WAITING",
            next_node_id=None,
            task_score=60,
            squad_available=0,
            nodes=[
                {
                    "nodeId": "S09",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "RED", "defense": 6, "active": True},
                },
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
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

        self.assertEqual([{"action": "WAIT"}], strategy.decide(state))

    def test_wuguan_trap_keeps_waiting_before_round_400_even_when_old_margin_is_tight(self) -> None:
        state = _state(
            "S10",
            round_no=356,
            player_state="WAITING",
            next_node_id=None,
            task_score=60,
            squad_available=0,
            weather={
                "active": [
                    {
                        "weatherId": "W_POLICY_03",
                        "type": "HOT",
                        "region": "ALL",
                        "remainRound": 37,
                    }
                ]
            },
            nodes=[
                {
                    "nodeId": "S09",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "RED", "defense": 6, "active": True},
                },
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
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

        self.assertEqual([{"action": "WAIT"}], strategy.decide(state))

    def test_wuguan_trap_sets_wuguan_guard_at_round_400_wait_limit(self) -> None:
        state = _state(
            "S10",
            round_no=400,
            player_state="WAITING",
            next_node_id=None,
            task_score=60,
            squad_available=0,
            nodes=[
                {
                    "nodeId": "S09",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "RED", "defense": 6, "active": True},
                },
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
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
            [{"action": "SET_GUARD", "targetNodeId": "S10", "extraGoodFruit": 2}],
            strategy.decide(state),
        )

    def test_wuguan_trap_sets_wuguan_guard_when_opponent_leaves_luoyang(self) -> None:
        state = _state(
            "S10",
            round_no=285,
            task_score=60,
            squad_available=0,
            nodes=[
                {"nodeId": "S09", "hasObstacle": False, "resourceStock": {}},
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "MOVING",
                    "currentNodeId": "S09",
                    "nextNodeId": "S10",
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "SET_GUARD", "targetNodeId": "S10", "extraGoodFruit": 2}],
            strategy.decide(state),
        )

    def test_wuguan_trap_does_not_set_wuguan_guard_when_opponent_too_close(self) -> None:
        state = _state(
            "S10",
            round_no=285,
            task_score=60,
            squad_available=0,
            nodes=[
                {"nodeId": "S09", "hasObstacle": False, "resourceStock": {}},
                {"nodeId": "S10", "hasObstacle": False, "resourceStock": {}},
            ],
            extra_players=[
                {
                    "playerId": 2002,
                    "teamId": "BLUE",
                    "state": "MOVING",
                    "currentNodeId": "S09",
                    "nextNodeId": "S10",
                    "edgeProgressMs": 8000,
                    "edgeTotalMs": 10000,
                }
            ],
        )
        strategy = build_strategy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S11"}],
            strategy.decide(state),
        )

    def test_strategy_profile_can_disable_wuguan_trap(self) -> None:
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
        strategy = build_strategy(
            Config(
                "127.0.0.1",
                30000,
                1001,
                "red",
                "0.1",
                strategy_profile="balanced",
            )
        )
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
