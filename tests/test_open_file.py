"""Tests for opening a file into a tab -- the success path and the failures.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib

import pytest

import viewer

tk = pytest.importorskip("tkinter")


@pytest.fixture
def errors(monkeypatch):
    """Records error dialogs instead of opening them."""
    shown = []
    monkeypatch.setattr(viewer.messagebox, "showerror", lambda title, msg: shown.append((title, msg)))
    return shown


@pytest.fixture
def app(tmp_path, monkeypatch, errors):
    # the app writes its settings on every open: keep that out of the real file
    monkeypatch.setattr(viewer, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(viewer, "CONFIG_FILE", str(tmp_path / "config" / "config.json"))
    try:
        a = viewer.CSVViewerApp()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    a.withdraw()
    yield a
    with contextlib.suppress(tk.TclError):
        a.destroy()


def good_file(tmp_path, name="ok.csv"):
    p = tmp_path / name
    p.write_text("a,b\n1,2\n", encoding="utf-8")
    return str(p)


def undecodable_file(tmp_path):
    # UTF-16 without a byte-order mark: read_csv_file refuses it
    p = tmp_path / "bad.csv"
    p.write_bytes("a,b\n1,2\n".encode("utf-16-le"))
    return str(p)


def csv_tabs(app):
    return [app.nametowidget(t) for t in app.notebook.tabs() if isinstance(app.nametowidget(t), viewer.CSVTab)]


class TestOpenFile:
    def test_a_good_file_gets_a_tab_and_a_recent_entry(self, app, tmp_path):
        path = good_file(tmp_path)

        app.open_file(path)

        assert [t.filepath for t in csv_tabs(app)] == [path]
        assert app.recent_files == [path]

    def test_a_file_that_cannot_be_read_leaves_no_blank_tab(self, app, tmp_path, errors):
        app.open_file(undecodable_file(tmp_path))

        assert csv_tabs(app) == []
        assert len(errors) == 1

    def test_a_file_that_cannot_be_read_is_not_added_to_recent_files(self, app, tmp_path, errors):
        app.open_file(undecodable_file(tmp_path))

        assert app.recent_files == []

    def test_the_empty_hint_survives_a_failed_open(self, app, tmp_path, errors):
        # nothing was opened, so the "(empty)" tab must still be the only one
        app.open_file(undecodable_file(tmp_path))

        assert [app.notebook.tab(t, "text") for t in app.notebook.tabs()] == ["(empty)"]

    def test_the_empty_hint_goes_away_once_a_file_opens(self, app, tmp_path):
        app.open_file(good_file(tmp_path))

        assert [app.notebook.tab(t, "text") for t in app.notebook.tabs()] == ["ok.csv"]

    def test_a_failed_open_does_not_disturb_the_tabs_already_open(self, app, tmp_path, errors):
        good = good_file(tmp_path)
        app.open_file(good)

        app.open_file(undecodable_file(tmp_path))

        assert [t.filepath for t in csv_tabs(app)] == [good]

    def test_opening_an_open_file_again_focuses_it_without_a_second_tab(self, app, tmp_path):
        path = good_file(tmp_path)
        app.open_file(path)
        other = good_file(tmp_path, "other.csv")
        app.open_file(other)

        app.open_file(path)

        assert len(csv_tabs(app)) == 2
        assert app.notebook.select() == str(csv_tabs(app)[0])
        assert app.recent_files[0] == path  # re-opening still counts as recent
