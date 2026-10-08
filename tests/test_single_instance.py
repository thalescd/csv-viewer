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


class TestRebinding:
    """Quitting and reopening must not lose the single-instance behaviour."""

    def test_port_can_be_rebound_right_after_a_handoff(self):
        srv = viewer.SingleInstanceServer(host=HOST, port=0)
        port = srv.port
        assert viewer.send_paths_to_running_instance(["/tmp/a.csv"], host=HOST, port=port)
        srv.close()
        # the handoff leaves the connection in TIME_WAIT; binding again anyway
        # is what SO_REUSEADDR buys us
        again = viewer.SingleInstanceServer(host=HOST, port=port)
        try:
            assert again.port == port
        finally:
            again.close()


def _raw_exchange(port, pieces, pause=0.2, wait_for_reply=True):
    """Sends `pieces` as separate writes, then returns whatever the server answers."""
    with socket.create_connection((HOST, port), timeout=3.0) as s:
        for piece in pieces:
            s.sendall(piece)
            time.sleep(pause)
        if not wait_for_reply:
            return b""
        s.settimeout(3.0)
        try:
            return s.recv(64)
        except OSError:
            return b""


class TestMessageFraming:
    """A handoff is one line of JSON; it may arrive in several pieces."""

    @pytest.fixture(autouse=True)
    def short_deadline(self, monkeypatch):
        # the server gives up on a message that never ends; do not wait the full time
        monkeypatch.setattr(viewer, "HANDOFF_READ_SECONDS", 0.5)

    def test_a_message_split_across_writes_is_read_whole(self, server):
        payload = viewer.encode_paths(["a.csv", "b.csv"])
        half = len(payload) // 2

        reply = _raw_exchange(server.port, [payload[:half], payload[half:]])

        assert reply == viewer.INSTANCE_ACK
        assert _wait_for_queue(server) == ["a.csv", "b.csv"]

    def test_a_long_list_of_paths_is_not_cut_short(self, server):
        # ~300 KB, well past a single read of 64 KB
        paths = [f"/data/folder/{i:05d}/{'x' * 80}.csv" for i in range(3000)]

        assert viewer.send_paths_to_running_instance(paths, host=HOST, port=server.port, timeout=5.0)
        assert _wait_for_queue(server) == paths

    def test_a_message_that_never_ends_is_not_acknowledged(self, server):
        # half a message and then silence: the sender must not be told its files
        # were taken, or it exits and they are lost
        payload = viewer.encode_paths(["a.csv"])

        reply = _raw_exchange(server.port, [payload[:-3]], pause=0.0)  # then silence

        assert reply != viewer.INSTANCE_ACK
        assert server.queue.empty()

    def test_a_connection_that_closes_early_is_not_acknowledged(self, server):
        with socket.create_connection((HOST, server.port), timeout=3.0) as s:
            s.sendall(b'["a.csv"')
            s.shutdown(socket.SHUT_WR)
            s.settimeout(3.0)
            assert s.recv(64) != viewer.INSTANCE_ACK
        assert server.queue.empty()

    def test_an_oversized_message_is_refused(self, server):
        reply = _raw_exchange(server.port, [b"x" * (viewer.MAX_HANDOFF_BYTES + 1000)], pause=0.0)

        assert reply != viewer.INSTANCE_ACK
        assert server.queue.empty()

    def test_the_server_keeps_serving_after_a_bad_connection(self, server):
        _raw_exchange(server.port, [b'["half'], pause=0.0)

        assert viewer.send_paths_to_running_instance(["ok.csv"], host=HOST, port=server.port)
        assert _wait_for_queue(server) == ["ok.csv"]


class TestUserPort:
    """Each user meets their own instance on their own port."""

    def test_the_same_user_always_gets_the_same_port(self):
        assert viewer.user_port("alice") == viewer.user_port("alice")

    def test_different_users_get_different_ports(self):
        names = ["alice", "bob", "carol", "joao.silva", "maria.souza", "thales"]

        assert len({viewer.user_port(n) for n in names}) == len(names)

    def test_the_port_is_in_the_unregistered_range(self):
        for name in ["", "alice", "COOP\\joao", "ação", "x" * 500]:
            assert 49152 <= viewer.user_port(name) <= 65151

    def test_the_default_is_the_current_users_port(self, monkeypatch):
        monkeypatch.setattr(viewer.getpass, "getuser", lambda: "alice")

        assert viewer.user_port() == viewer.user_port("alice")

    @pytest.mark.parametrize("error", [KeyError("LOGNAME"), OSError("no such user"), ImportError("pwd")])
    def test_an_unknown_user_still_gets_a_working_port(self, monkeypatch, error):
        def boom():
            raise error

        monkeypatch.setattr(viewer.getpass, "getuser", boom)

        assert viewer.user_port() == viewer.user_port("")

    def test_the_module_default_is_this_users_port(self):
        assert viewer.user_port() == viewer.SINGLE_INSTANCE_PORT

    def test_two_users_do_not_hand_files_to_each_other(self):
        # alice's instance is running; bob's launch looks on bob's port, finds
        # nothing, and so opens a window of his own instead of using alice's
        alice = viewer.SingleInstanceServer(host=HOST, port=viewer.user_port("alice"))
        try:
            bobs_port = viewer.user_port("bob")
            delivered = viewer.send_paths_to_running_instance(["bob.csv"], host=HOST, port=bobs_port)

            assert delivered is False
            assert alice.queue.empty()
        finally:
            alice.close()
