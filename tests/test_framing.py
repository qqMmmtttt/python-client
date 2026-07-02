import socket
import unittest
import json

from lychee_basic_client.framing import encode_frame, read_frame, write_frame
from lychee_basic_client.protocol.actions import action_message, verify_gate


class FramingTests(unittest.TestCase):
    def test_write_and_read_frame(self) -> None:
        left, right = socket.socketpair()
        try:
            write_frame(left, {"msg_name": "ping"})
            self.assertEqual({"msg_name": "ping"}, read_frame(right))
        finally:
            left.close()
            right.close()

    def test_verify_gate_break_order_frame_matches_protocol_boundaries(self) -> None:
        message = action_message(
            "local-debug-l1",
            460,
            1001,
            [verify_gate("S14", rush_tactic="BREAK_ORDER")],
        )

        frame = encode_frame(message)
        body = frame[5:]

        self.assertEqual(b"00174", frame[:5])
        self.assertEqual(174, len(body))
        self.assertEqual(b"{", body[:1])
        self.assertEqual(message, json.loads(body.decode("utf-8")))


if __name__ == "__main__":
    unittest.main()
