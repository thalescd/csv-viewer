"""Tests for turning a clicked column into a data column.

A click reports a column as "#n": a 1-based position on screen, which a drag
may have reordered. The rows are indexed by the column's own position in the
header. Mixing the two reads the neighbouring column -- these pin that down.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib

import pytest

import viewer

tk = pytest.importorskip("tkinter")

HEADER = ["nome", "idade", "cidade"]
ROWS = [
    ["zeca", "10", "porto"],
    ["ana", "30", "bage"],
    ["bia", "20", "caxias"],
]


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    r.withdraw()
    yield r
    with contextlib.suppress(tk.TclError):
        r.destroy()


@pytest.fixture
def tab(root, tmp_path):
    path = tmp_path / "people.csv"
    path.write_text(
        "\n".join([",".join(HEADER)] + [",".join(r) for r in ROWS]) + "\n",
        encoding="utf-8",
    )
    widget = viewer.CSVTab(root, filepath=str(path))
    widget.pack(fill="both", expand=True)
    root.update()
    return widget


def shown_rows(tab):
    return [tab._rows_by_iid[iid] for iid in tab.tree.get_children("")]


class TestDataColumn:
    def test_the_first_display_column_is_the_first_data_column(self, tab):
        assert tab._data_column("#1") == "c0"

    def test_a_name_is_returned_as_is(self, tab):
        assert tab._data_column("c2") == "c2"

    def test_a_position_past_the_last_column_is_none(self, tab):
        assert tab._data_column("#4") is None

    def test_an_unknown_name_is_none(self, tab):
        assert tab._data_column("c9") is None

    def test_nothing_clicked_is_none(self, tab):
        assert tab._data_column("") is None

    def test_it_follows_the_columns_as_reordered(self, tab):
        tab._reorder_columns("c0", "c2")  # nome moves to the end
        assert tab._data_column("#3") == "c0"


class TestSortByClickedColumn:
    def test_clicking_a_header_sorts_by_that_column(self, tab):
        tab._sort_by("#1")  # the "nome" header
        assert [r[0] for r in shown_rows(tab)] == ["ana", "bia", "zeca"]

    def test_the_arrow_lands_on_the_column_that_was_clicked(self, tab):
        tab._sort_by("#1")
        assert tab.tree.heading("c0", "text") == "nome ▲"
        assert tab.tree.heading("c1", "text") == "idade"

    def test_the_last_column_sorts_like_any_other(self, tab):
        # "#3" read as an index used to run off the end of the header
        tab._sort_by("#3")
        assert [r[2] for r in shown_rows(tab)] == ["bage", "caxias", "porto"]

    def test_a_second_click_reverses_it(self, tab):
        tab._sort_by("#1")
        tab._sort_by("#1")
        assert [r[0] for r in shown_rows(tab)] == ["zeca", "bia", "ana"]


class TestSelectionDrivenCopies:
    def test_a_clicked_cell_is_remembered_by_name_not_by_position(self, tab, monkeypatch):
        first = tab.tree.get_children("")[0]
        # the window is withdrawn here, so nothing has pixel coordinates to
        # click at: stand in for what a click over the second column reports
        monkeypatch.setattr(tab.tree, "identify_row", lambda y: first)
        monkeypatch.setattr(tab.tree, "identify_column", lambda x: "#2")

        tab._select_cell(10, 10)

        # "#2" would go stale the moment a column is dragged elsewhere
        assert tab._selected_cell == (first, "c1")
