import logging
import socket
import tempfile
import threading
import unittest

from lychee_basic_client.config import Config
from lychee_basic_client.observability.logging_setup import setup_logging
from lychee_basic_client.runtime.session import ClientSession
from lychee_basic_client.testing.fixtures import sample_inquire, sample_start
from lychee_basic_client.testing.mock_server import ScriptedMockServer


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
                logging.shutdown()

        self.assertEqual(0, result)
        self.assertEqual("registration", server.received[0]["msg_name"])
        self.assertEqual("ready", server.received[1]["msg_name"])
        self.assertEqual("action", server.received[2]["msg_name"])
        self.assertEqual([], server.received[2]["msg_data"]["actions"])


if __name__ == "__main__":
    unittest.main()
