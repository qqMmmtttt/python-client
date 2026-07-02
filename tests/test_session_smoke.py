import logging
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from lychee_basic_client.config import Config
from lychee_basic_client.observability.logging_setup import setup_logging
from lychee_basic_client.protocol.framing import read_frame, write_frame
from lychee_basic_client.runtime.session import ClientSession
from lychee_basic_client.testing.fixtures import sample_inquire, sample_start
from lychee_basic_client.testing.mock_server import ScriptedMockServer


def _close_package_handlers() -> None:
    logger = logging.getLogger("lychee_basic_client")
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
    logger.handlers.clear()


class SessionSmokeTests(unittest.TestCase):
    def test_session_sends_registration_ready_and_heartbeat_action(self) -> None:
        client_sock, server_sock = socket.socketpair()
        server = ScriptedMockServer(
            server_sock,
            [
                {"msg_name": "start", "msg_data": sample_start()},
                {"msg_name": "inquire", "msg_data": sample_inquire(round_no=1)},
            ],
        )

        trace_text = ""
        important_text = ""
        with tempfile.TemporaryDirectory() as tmp_dir:
            setup_logging(tmp_dir, "ERROR")
            thread = threading.Thread(target=server.run)
            thread.start()
            try:
                result = ClientSession(
                    client_sock,
                    Config("127.0.0.1", 30000, 1006, "BasicPy", "0.1"),
                ).run()
            finally:
                client_sock.close()
                thread.join(timeout=2)
                _close_package_handlers()
                trace_text = (Path(tmp_dir) / "trace.log").read_text(encoding="utf-8")
                important_text = (Path(tmp_dir) / "important.log").read_text(encoding="utf-8")

        self.assertEqual(0, result)
        self.assertEqual("registration", server.received[0]["msg_name"])
        self.assertEqual("ready", server.received[1]["msg_name"])
        self.assertEqual("action", server.received[2]["msg_name"])
        self.assertEqual([], server.received[2]["msg_data"]["actions"])
        self.assertIn("wire direction=outbound msg_name=registration", trace_text)
        self.assertIn("wire direction=inbound msg_name=start", trace_text)
        self.assertIn("body_bytes=", trace_text)
        self.assertIn("decision round=1 strategy=none actions=[]", important_text)

    def test_in_game_error_does_not_close_session_before_next_inquire(self) -> None:
        client_sock, server_sock = socket.socketpair()
        received = []

        def server_run() -> None:
            try:
                received.append(read_frame(server_sock))
                write_frame(server_sock, {"msg_name": "start", "msg_data": sample_start()})
                received.append(read_frame(server_sock))
                write_frame(server_sock, {"msg_name": "inquire", "msg_data": sample_inquire(round_no=1)})
                received.append(read_frame(server_sock))
                write_frame(
                    server_sock,
                    {
                        "msg_name": "error",
                        "msg_data": {
                            "round": 1,
                            "playerId": 1006,
                            "errorCode": "INVALID_JSON",
                            "message": "test parser error",
                        },
                    },
                )
                write_frame(server_sock, {"msg_name": "inquire", "msg_data": sample_inquire(round_no=2)})
                received.append(read_frame(server_sock))
            finally:
                server_sock.close()

        with tempfile.TemporaryDirectory() as tmp_dir:
            setup_logging(tmp_dir, "ERROR")
            thread = threading.Thread(target=server_run)
            thread.start()
            try:
                result = ClientSession(
                    client_sock,
                    Config("127.0.0.1", 30000, 1006, "BasicPy", "0.1"),
                ).run()
            finally:
                client_sock.close()
                thread.join(timeout=2)
                _close_package_handlers()

        self.assertEqual(0, result)
        self.assertEqual("action", received[2]["msg_name"])
        self.assertEqual(1, received[2]["msg_data"]["round"])
        self.assertEqual("action", received[3]["msg_name"])
        self.assertEqual(2, received[3]["msg_data"]["round"])


if __name__ == "__main__":
    unittest.main()
