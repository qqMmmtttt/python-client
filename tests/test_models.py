import unittest
import json
from pathlib import Path

from lychee_basic_client.models.map import GameMap
from lychee_basic_client.models.state import GameState
from lychee_basic_client.testing.fixtures import sample_inquire, sample_start


class ModelTests(unittest.TestCase):
    def test_start_state_parses_roles_and_neighbors(self) -> None:
        state = GameState.from_start(sample_start(), 1006)

        self.assertEqual("match-test", state.match_id)
        self.assertEqual("S01", state.game_map.start_node_id)
        self.assertEqual("S14", state.game_map.gate_node_id)
        self.assertEqual(["S15"], state.game_map.terminal_node_ids)
        self.assertEqual(["S02"], state.game_map.neighbors("S01"))

    def test_inquire_state_preserves_previous_map(self) -> None:
        start_state = GameState.from_start(sample_start(), 1006)
        state = GameState.from_inquire(sample_inquire(round_no=9), 1006, start_state.game_map)

        self.assertEqual(9, state.round_no)
        self.assertEqual("S01", state.me.current_node_id)
        self.assertEqual(["S02"], state.game_map.neighbors("S01"))

    def test_real_map_config_parses_roles_edges_and_process_nodes(self) -> None:
        map_config = json.loads(Path("example_data/map_config.json").read_text(encoding="utf-8"))
        game_map = GameMap.from_start(map_config)

        self.assertEqual("S01", game_map.start_node_id)
        self.assertEqual("S14", game_map.gate_node_id)
        self.assertEqual(["S15"], game_map.terminal_node_ids)
        self.assertEqual(15, len(game_map.nodes))
        self.assertEqual(21, len(game_map.edges))
        self.assertEqual("TRANSFER", game_map.process_nodes["S02"].process_type)
        self.assertEqual("VERIFY", game_map.process_nodes["S14"].process_type)

    def test_route_distance_uses_configured_edge_distances(self) -> None:
        map_config = json.loads(Path("example_data/map_config.json").read_text(encoding="utf-8"))
        game_map = GameMap.from_start(map_config)

        self.assertEqual(18, game_map.route_distance("S13", "S14"))
        self.assertEqual(10, game_map.route_distance("S14", "S15"))
        self.assertIsNone(game_map.route_distance("S01", "missing"))


if __name__ == "__main__":
    unittest.main()
