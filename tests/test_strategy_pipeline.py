import unittest
from typing import Any

from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.context import StrategyContext
from lychee_basic_client.strategies.control import force_empty_actions
from lychee_basic_client.strategies.pipeline import StrategyPipeline
from lychee_basic_client.testing.fixtures import sample_start


class EmptyStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return []


class MoveStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return [{"action": "MOVE", "targetNodeId": "S02"}]


class OtherMoveStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return [{"action": "MOVE", "targetNodeId": "S14"}]


class SquadStrategyStub:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return [{"action": "SQUAD_SCOUT", "targetNodeId": "S04"}]


class IntelStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return [{"action": "USE_RESOURCE", "resourceType": "INTEL", "targetNodeId": "S11"}]


class ClearStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return [{"action": "CLEAR", "targetNodeId": "S10"}]


class ForceEmptyStrategy:
    def on_start(self, state: GameState) -> None:
        return None

    def decide(self, context: StrategyContext) -> list[dict[str, Any]]:
        return [force_empty_actions("test")]


class StrategyPipelineTests(unittest.TestCase):
    def test_pipeline_uses_first_main_action(self) -> None:
        state = GameState.from_start(sample_start(), 1006)
        pipeline = StrategyPipeline([EmptyStrategy(), MoveStrategy(), OtherMoveStrategy()])

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S02"}],
            pipeline.decide(state),
        )

    def test_pipeline_combines_main_and_squad_actions(self) -> None:
        state = GameState.from_start(sample_start(), 1006)
        pipeline = StrategyPipeline([SquadStrategyStub(), MoveStrategy()])

        self.assertEqual(
            [
                {"action": "MOVE", "targetNodeId": "S02"},
                {"action": "SQUAD_SCOUT", "targetNodeId": "S04"},
            ],
            pipeline.decide(state),
        )

    def test_pipeline_replaces_lower_priority_main_action(self) -> None:
        state = GameState.from_start(sample_start(), 1006)
        pipeline = StrategyPipeline([IntelStrategy(), ClearStrategy()])

        self.assertEqual(
            [{"action": "CLEAR", "targetNodeId": "S10"}],
            pipeline.decide(state),
        )

    def test_force_empty_action_clears_previously_selected_actions(self) -> None:
        state = GameState.from_start(sample_start(), 1006)
        pipeline = StrategyPipeline([SquadStrategyStub(), MoveStrategy(), ForceEmptyStrategy()])

        self.assertEqual([], pipeline.decide(state))


if __name__ == "__main__":
    unittest.main()
