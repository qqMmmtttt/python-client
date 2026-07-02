import unittest
from typing import Any

from lychee_basic_client.models.state import GameState
from lychee_basic_client.strategies.context import StrategyContext
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


class StrategyPipelineTests(unittest.TestCase):
    def test_pipeline_uses_first_non_empty_strategy(self) -> None:
        state = GameState.from_start(sample_start(), 1006)
        pipeline = StrategyPipeline([EmptyStrategy(), MoveStrategy()])

        self.assertEqual(
            [{"action": "MOVE", "targetNodeId": "S02"}],
            pipeline.decide(state),
        )


if __name__ == "__main__":
    unittest.main()
