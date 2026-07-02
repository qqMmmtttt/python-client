import unittest
from typing import Optional

from lychee_basic_client.config import Config
from lychee_basic_client.models.state import GameState, PlayerState
from lychee_basic_client.rules.legal import can_submit_main_action
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.delivery import DeliveryStrategy
from lychee_basic_client.strategies.resources import ResourceStrategy
from lychee_basic_client.strategies.routing import RoutePolicy
from lychee_basic_client.strategies.rush import RushStrategy
from lychee_basic_client.strategies.tasks import TaskStrategy


def _state(
    player_state: str,
    *,
    node_id: str = "S12",
    phase: str = "NORMAL",
    resources: Optional[dict[str, int]] = None,
    freshness: float = 50,
    good_fruit: int = 100,
    round_no: int = 403,
) -> GameState:
    player = PlayerState(
        player_id=1001,
        team_id="RED",
        state=player_state,
        current_node_id=node_id,
        next_node_id="S13" if player_state in {"MOVING", "WAITING"} else None,
        freshness=freshness,
        good_fruit=good_fruit,
        task_score=30,
        resources=resources or {},
        raw={"buffs": []},
    )
    return GameState(
        match_id="route-edge-test",
        round_no=round_no,
        player_id=1001,
        phase=phase,
        players={1001: player},
        tasks=[
            {
                "taskId": "task-at-current-node",
                "taskTemplateId": "T01",
                "nodeId": "S12",
                "score": 30,
                "active": True,
            }
        ],
    )


class RouteEdgeStateTests(unittest.TestCase):
    def test_ice_box_is_not_used_while_waiting_on_route_edge(self) -> None:
        state = _state("WAITING", resources={"ICE_BOX": 1})

        self.assertEqual([], ResourceStrategy().decide(StrategyContext.from_state(state)))

    def test_ice_box_is_not_used_while_moving_on_route_edge(self) -> None:
        state = _state("MOVING", resources={"ICE_BOX": 1})

        self.assertEqual([], ResourceStrategy().decide(StrategyContext.from_state(state)))

    def test_horse_resource_can_be_used_on_route_edge(self) -> None:
        state = _state("WAITING", resources={"FAST_HORSE": 1, "ICE_BOX": 1})

        self.assertEqual(
            [{"action": "USE_RESOURCE", "resourceType": "FAST_HORSE"}],
            ResourceStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_terminal_does_not_use_ice_box_before_delivery(self) -> None:
        state = _state("IDLE", node_id="S15", resources={"ICE_BOX": 1})

        self.assertEqual([], ResourceStrategy().decide(StrategyContext.from_state(state)))

    def test_rush_speed_can_be_used_on_late_route_edge(self) -> None:
        state = _state("MOVING", phase="RUSH", round_no=535, good_fruit=80)

        self.assertEqual(
            [{"action": "RUSH_SPEED"}],
            RushStrategy().decide(StrategyContext.from_state(state)),
        )

    def test_station_task_strategy_does_not_run_while_waiting_on_route_edge(self) -> None:
        state = _state("WAITING")

        self.assertEqual([], TaskStrategy().decide(StrategyContext.from_state(state)))

    def test_delivery_strategy_resumes_waiting_route_edge_to_existing_target(self) -> None:
        state = _state("WAITING")
        strategy = DeliveryStrategy(
            RoutePolicy(Config("127.0.0.1", 30000, 1001, "red", "0.1"))
        )

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S13"}],
            strategy.decide(StrategyContext.from_state(state)),
        )

    def test_waiting_is_not_a_normal_main_action_state(self) -> None:
        self.assertFalse(can_submit_main_action(_state("WAITING")))


if __name__ == "__main__":
    unittest.main()
