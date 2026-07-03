import json
import unittest
from pathlib import Path
from typing import Any, Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.delivery import DeliveryStrategy
from lychee_basic_client.strategies.routing import RoutePolicy
from lychee_basic_client.strategies.tasks import TaskStrategy


def _map_config() -> dict[str, Any]:
    return json.loads(Path("example_data/map_config.json").read_text(encoding="utf-8"))


def _state(
    node_id: str,
    *,
    round_no: int = 1,
    player_state: str = "IDLE",
    next_node_id: Optional[str] = None,
    task_score: int = 0,
    good_fruit: int = 100,
    bad_fruit: int = 0,
    tasks: Optional[list[dict[str, Any]]] = None,
    nodes: Optional[list[dict[str, Any]]] = None,
    events: Optional[list[dict[str, Any]]] = None,
    action_results: Optional[list[dict[str, Any]]] = None,
) -> GameState:
    map_config = _map_config()
    return GameState.from_start(
        {
            "matchId": "match-real-map",
            "round": round_no,
            "nodes": map_config["nodes"],
            "edges": map_config["edges"],
            "processNodes": map_config["processNodes"],
            "players": [
                {
                    "playerId": 1001,
                    "teamId": "RED",
                    "state": player_state,
                    "currentNodeId": node_id,
                    "nextNodeId": next_node_id,
                    "goodFruit": good_fruit,
                    "badFruit": bad_fruit,
                    "freshness": 90,
                    "taskScore": task_score,
                    "resources": {},
                }
            ],
            "tasks": tasks or [],
        },
        1001,
    ).__class__.from_inquire(
        {
            "matchId": "match-real-map",
            "round": round_no,
            "phase": "NORMAL",
            "players": [
                {
                    "playerId": 1001,
                    "teamId": "RED",
                    "state": player_state,
                    "currentNodeId": node_id,
                    "nextNodeId": next_node_id,
                    "goodFruit": good_fruit,
                    "badFruit": bad_fruit,
                    "freshness": 90,
                    "taskScore": task_score,
                    "resources": {},
                }
            ],
            "nodes": nodes or [],
            "tasks": tasks or [],
            "events": events or [],
            "contests": [],
            "actionResults": action_results or [],
        },
        1001,
        GameState.from_start(
            {
                "matchId": "match-real-map",
                "round": 1,
                "nodes": map_config["nodes"],
                "edges": map_config["edges"],
                "processNodes": map_config["processNodes"],
                "players": [],
            },
            1001,
        ).game_map,
    )


class TaskPlanningTests(unittest.TestCase):
    def test_claims_high_value_task_at_current_node(self) -> None:
        task = {
            "taskId": "task-t01",
            "taskTemplateId": "T01",
            "nodeId": "S03",
            "score": 30,
            "active": True,
        }
        state = _state("S03", tasks=[task])

        self.assertEqual(
            [{"action": "CLAIM_TASK", "taskId": "task-t01"}],
            TaskStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_task_strategy_does_not_repeat_rejected_task(self) -> None:
        task = {
            "taskId": "task-rejected",
            "taskTemplateId": "T01",
            "nodeId": "S03",
            "score": 30,
            "active": True,
        }
        strategy = TaskStrategy()
        strategy.on_start(_state("S03", tasks=[task]))
        rejected_state = _state("S03", tasks=[task])
        rejected_state.events = [
            {
                "type": "ACTION_REJECTED",
                "payload": {
                    "playerId": 1001,
                    "action": "CLAIM_TASK",
                    "taskId": "task-rejected",
                    "errorCode": "OBJECT_BUSY",
                },
            }
        ]

        self.assertEqual([], strategy.decide(StrategyContext.from_state(rejected_state)))

    def test_delivery_routes_to_reachable_task_before_gate_when_safe(self) -> None:
        task = {
            "taskId": "task-t02",
            "taskTemplateId": "T02",
            "nodeId": "S07",
            "score": 30,
            "active": True,
            "processRound": 4,
        }
        state = _state("S03", tasks=[task])
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S07"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivery_stops_pursuing_tasks_after_cutoff(self) -> None:
        task = {
            "taskId": "late-task",
            "taskTemplateId": "T02",
            "nodeId": "S06",
            "score": 30,
            "active": True,
            "processRound": 4,
        }
        state = _state("S03", round_no=430, tasks=[task])
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S07"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_t04_obstacle_task_is_preferred_over_clear(self) -> None:
        task = {
            "taskId": "task-t04",
            "taskTemplateId": "T04",
            "nodeId": "S10",
            "score": 30,
            "active": True,
            "processRound": 6,
        }
        state = _state(
            "S09",
            tasks=[task],
            nodes=[{"nodeId": "S10", "hasObstacle": True, "resourceStock": {}}],
        )
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "CLAIM_TASK", "taskId": "task-t04"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivery_breaks_enemy_guard_when_one_action_can_clear_it(self) -> None:
        state = _state(
            "S10",
            nodes=[
                {
                    "nodeId": "S11",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 2, "active": True},
                }
            ],
        )
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "BREAK_GUARD", "targetNodeId": "S11", "goodFruit": 1, "badFruit": 0}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivery_breaks_enemy_guard_with_correct_attack_value(self) -> None:
        state = _state(
            "S10",
            nodes=[
                {
                    "nodeId": "S11",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 4, "active": True},
                }
            ],
        )
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "BREAK_GUARD", "targetNodeId": "S11", "goodFruit": 2, "badFruit": 0}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivery_forces_pass_when_enemy_guard_is_too_strong_to_break_once(self) -> None:
        state = _state(
            "S10",
            nodes=[
                {
                    "nodeId": "S11",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 7, "active": True},
                }
            ],
        )
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "FORCED_PASS", "targetNodeId": "S11"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivery_clears_guarded_obstacle_before_breaking_guard(self) -> None:
        state = _state(
            "S10",
            nodes=[
                {
                    "nodeId": "S11",
                    "hasObstacle": True,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 2, "active": True},
                }
            ],
        )
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "CLEAR", "targetNodeId": "S11"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivery_recovers_from_hidden_move_blocked_by_guard(self) -> None:
        state = _state(
            "S10",
            events=[
                {
                    "type": "ACTION_REJECTED",
                    "payload": {
                        "playerId": 1001,
                        "action": "MOVE",
                        "targetNodeId": "S11",
                        "errorCode": "MOVE_BLOCKED_BY_GUARD",
                    },
                }
            ],
        )
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(state)

        self.assertEqual(
            [{"action": "FORCED_PASS", "targetNodeId": "S11"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_delivery_waits_on_route_edge_after_move_is_blocked_without_target_payload(self) -> None:
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(_state("S09"))
        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S10"}],
            strategy.decide(StrategyContext.from_state(_state("S09"))),
        )

        blocked = _state(
            "S09",
            player_state="MOVING",
            next_node_id="S10",
            bad_fruit=1,
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 3, "active": True},
                }
            ],
            events=[
                {
                    "type": "ACTION_REJECTED",
                    "payload": {
                        "playerId": 1001,
                        "action": "MOVE",
                        "errorCode": "MOVE_BLOCKED_BY_GUARD",
                    },
                }
            ],
            action_results=[
                {
                    "round": 289,
                    "playerId": 1001,
                    "action": "MOVE",
                    "accepted": False,
                    "result": "ACTION_REJECTED",
                    "errorCode": "MOVE_BLOCKED_BY_GUARD",
                }
            ],
        )

        self.assertEqual([], strategy.decide(StrategyContext.from_state(blocked)))

        settled = _state(
            "S09",
            bad_fruit=1,
            nodes=[
                {
                    "nodeId": "S10",
                    "hasObstacle": False,
                    "resourceStock": {},
                    "guard": {"ownerTeamId": "BLUE", "defense": 3, "active": True},
                }
            ],
        )
        self.assertEqual(
            [{"action": "BREAK_GUARD", "targetNodeId": "S10", "goodFruit": 0, "badFruit": 1}],
            strategy.decide(StrategyContext.from_state(settled)),
        )

    def test_delivery_does_not_force_pass_while_still_on_route_edge(self) -> None:
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )
        strategy.on_start(_state("S09"))
        strategy.decide(StrategyContext.from_state(_state("S09")))

        blocked = _state(
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
            events=[
                {
                    "type": "ACTION_REJECTED",
                    "payload": {
                        "playerId": 1001,
                        "action": "MOVE",
                        "errorCode": "MOVE_BLOCKED_BY_GUARD",
                    },
                }
            ],
        )

        self.assertEqual([], strategy.decide(StrategyContext.from_state(blocked)))


if __name__ == "__main__":
    unittest.main()
