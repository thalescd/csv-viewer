"""Tests for the single-instance handoff (loopback socket, no GUI involved)."""
import socket
import threading
import time

import pytest

import viewer

HOST = "127.0.0.1"


@pytest.fixture
def server():
    """A server on an ephemeral port, so tests never fight over the real one."""
    srv = viewer.SingleInstanceServer(host=HOST, port=0)
    yield srv
    srv.close()


def _wait_for_queue(srv, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not srv.queue.empty():
            return srv.queue.get_nowait()
        time.sleep(0.02)
    raise AssertionError("nothing arrived on the queue")


class TestPayloadEncoding:
    def test_round_trip(self):
        paths = [r"C:\data\a.csv", "/tmp/b.tsv"]
        assert viewer.decode_paths(viewer.encode_paths(paths)) == paths

    def test_round_trip_with_non_ascii(self):
        paths = [r"C:\dados\relatório anual.csv"]
        assert viewer.decode_paths(viewer.encode_paths(paths)) == paths

    def test_empty_list_round_trip(self):
        assert viewer.decode_paths(viewer.encode_paths([])) == []

    def test_garbage_is_ignored(self):
        assert viewer.decode_paths(b"not json at all") == []

    def test_wrong_json_shape_is_ignored(self):
        assert viewer.decode_paths(b'{"paths": ["a.csv"]}') == []

    def test_non_string_entries_are_dropped(self):
        assert viewer.decode_paths(b'["a.csv", 42, null]') == ["a.csv"]


class TestHandoff:
    def test_paths_reach_the_running_instance(self, server):
        delivered = viewer.send_paths_to_running_instance(
            ["a.csv", "b.csv"], host=HOST, port=server.port
        )

        assert delivered is True
        assert _wait_for_queue(server) == ["a.csv", "b.csv"]

    def test_empty_handoff_still_acknowledged(self, server):
        # launching the app with no file should still surface the open window
        assert viewer.send_paths_to_running_instance([], host=HOST, port=server.port) is True
        assert _wait_for_queue(server) == []

    def test_several_handoffs_queue_up(self, server):
        viewer.send_paths_to_running_instance(["one.csv"], host=HOST, port=server.port)
        viewer.send_paths_to_running_instance(["two.csv"], host=HOST, port=server.port)

        assert _wait_for_queue(server) == ["one.csv"]
        assert _wait_for_queue(server) == ["two.csv"]

    def test_returns_false_when_nobody_is_listening(self):
        # grab a port, then free it, so we know it is closed
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((HOST, 0))
        port = s.getsockname()[1]
        s.close()

        assert viewer.send_paths_to_running_instance(["a.csv"], host=HOST, port=port,
                                                     timeout=0.5) is False

    def test_returns_false_when_the_port_belongs_to_another_program(self):
        """A stranger on our port must not swallow the user's file silently."""
        impostor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        impostor.bind((HOST, 0))
        impostor.listen(1)
        port = impostor.getsockname()[1]

        def accept_and_say_nothing_useful():
            conn, _ = impostor.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(b"who are you?\n")

        t = threading.Thread(target=accept_and_say_nothing_useful, daemon=True)
        t.start()
        try:
            delivered = viewer.send_paths_to_running_instance(
                ["a.csv"], host=HOST, port=port, timeout=1.0
            )
            assert delivered is False  # caller must open its own window instead
        finally:
            t.join(timeout=2)
            impostor.close()

    def test_second_server_on_same_port_is_refused(self, server):
        """The port is the lock: only one instance can hold it."""
        with pytest.raises(OSError):
            viewer.SingleInstanceServer(host=HOST, port=server.port)
