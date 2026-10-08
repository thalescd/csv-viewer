"""Tests for opening a file into a tab -- the success path and the failures.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import pytest

import viewer

tk = pytest.importorskip("tkinter")


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


@pytest.fixture
def asked(monkeypatch):
    """Records the "large file" question, answered by `asked.answer`."""
    class Asked(list):
        answer = True

    log = Asked()

    def fake(title, message, **_kw):
        log.append((title, message))
        return log.answer

    monkeypatch.setattr(viewer.messagebox, "askyesno", fake)
    monkeypatch.setattr(viewer, "MAX_ROWS_WARN", 2)
    return log


def big_file(tmp_path, rows=5, name="big.csv"):
    p = tmp_path / name
    p.write_text("a,b\n" + "".join(f"{i},x\n" for i in range(rows)), encoding="utf-8")
    return str(p)


class TestLargeFile:
    def test_a_small_file_opens_without_a_question(self, app, tmp_path, asked):
        app.open_file(big_file(tmp_path, rows=2))

        assert asked == []
        assert len(csv_tabs(app)) == 1

    def test_a_large_file_asks_first_and_says_how_many_rows(self, app, tmp_path, asked):
        app.open_file(big_file(tmp_path, rows=5))

        assert len(asked) == 1
        assert "5 rows" in asked[0][1]

    def test_saying_yes_opens_it_and_notes_it_is_large(self, app, tmp_path, asked):
        asked.answer = True

        app.open_file(big_file(tmp_path, rows=5))

        (tab,) = csv_tabs(app)
        assert len(tab.rows) == 5
        assert "large file" in tab.status_var.get()

    def test_saying_no_opens_nothing_and_remembers_nothing(self, app, tmp_path, asked):
        asked.answer = False

        app.open_file(big_file(tmp_path, rows=5))

        assert csv_tabs(app) == []
        assert app.recent_files == []
        assert [app.notebook.tab(t, "text") for t in app.notebook.tabs()] == ["(empty)"]

    def test_saying_no_to_a_reload_keeps_what_was_showing(self, app, tmp_path, asked):
        path = big_file(tmp_path, rows=2)
        app.open_file(path)
        (tab,) = csv_tabs(app)
        status = tab.status_var.get()
        big_file(tmp_path, rows=9)  # the file grew behind our back
        asked.answer = False

        tab.reload()

        assert len(tab.rows) == 2
        assert tab.status_var.get() == status

    def test_the_busy_cursor_is_put_back_afterwards(self, app, tmp_path, asked):
        app.open_file(big_file(tmp_path, rows=5))

        assert str(app.cget("cursor")) == ""

    def test_the_busy_cursor_is_put_back_after_a_failure(self, app, tmp_path, errors):
        app.open_file(undecodable_file(tmp_path))

        assert str(app.cget("cursor")) == ""


class TestHugeFileOnDisk:
    """The size on disk is checked before reading: the row count comes too late."""

    @pytest.fixture
    def size_asked(self, monkeypatch):
        class Asked(list):
            answer = True

        log = Asked()

        def fake(title, message, **_kw):
            log.append(message)
            return log.answer

        monkeypatch.setattr(viewer.messagebox, "askyesno", fake)
        monkeypatch.setattr(viewer, "MAX_FILE_BYTES_WARN", 5)  # bytes: the test files are 8+, so "huge"
        return log

    @pytest.fixture
    def never_read(self, monkeypatch):
        def boom(*_a, **_k):
            raise AssertionError("the file was read although the user said no")

        monkeypatch.setattr(viewer, "read_csv_file", boom)

    def test_a_file_under_the_limit_opens_without_a_question(self, app, tmp_path, size_asked, monkeypatch):
        monkeypatch.setattr(viewer, "MAX_FILE_BYTES_WARN", 10_000)

        app.open_file(good_file(tmp_path))

        assert size_asked == []
        assert len(csv_tabs(app)) == 1

    def test_a_file_over_the_limit_asks_with_its_size_and_a_memory_estimate(self, app, tmp_path, size_asked):
        app.open_file(good_file(tmp_path))

        assert len(size_asked) == 1
        assert "ok.csv is 0 MB" in size_asked[0]
        assert "GB of memory" in size_asked[0]

    def test_saying_no_does_not_read_the_file_at_all(self, app, tmp_path, size_asked, never_read):
        size_asked.answer = False

        app.open_file(good_file(tmp_path))

        assert csv_tabs(app) == []
        assert app.recent_files == []
        assert [app.notebook.tab(t, "text") for t in app.notebook.tabs()] == ["(empty)"]

    def test_saying_yes_opens_it_and_notes_it_is_large(self, app, tmp_path, size_asked):
        app.open_file(good_file(tmp_path))

        (tab,) = csv_tabs(app)
        assert len(tab.rows) == 1
        assert "large file" in tab.status_var.get()

    def test_saying_yes_to_the_size_does_not_ask_again_about_the_rows(self, app, tmp_path, size_asked, monkeypatch):
        monkeypatch.setattr(viewer, "MAX_ROWS_WARN", 2)

        app.open_file(big_file(tmp_path, rows=5))

        assert len(size_asked) == 1  # one question, not one for the size and one for the rows
        assert len(csv_tabs(app)) == 1

    def test_saying_no_to_a_reload_keeps_what_was_showing(self, app, tmp_path, size_asked, monkeypatch):
        monkeypatch.setattr(viewer, "MAX_FILE_BYTES_WARN", 10_000)
        path = good_file(tmp_path)
        app.open_file(path)
        (tab,) = csv_tabs(app)
        status = tab.status_var.get()
        monkeypatch.setattr(viewer, "MAX_FILE_BYTES_WARN", 5)
        size_asked.answer = False

        tab.reload()

        assert len(tab.rows) == 1
        assert tab.status_var.get() == status

    def test_a_path_that_cannot_be_measured_is_left_to_the_normal_error(self, app, tmp_path, size_asked, errors):
        tab = viewer.CSVTab(app.notebook)

        assert tab.load(str(tmp_path / "missing.csv")) is False

        assert size_asked == []  # no size to ask about
        assert len(errors) == 1  # the usual error dialog instead
