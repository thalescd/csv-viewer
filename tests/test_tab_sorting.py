"""Tests for sorting a tab by clicking a column.

The row order is applied to the widget in one go, so these pin down that what
ends up on screen is the order that was asked for: the values, the zebra
stripes and the arrow on the header.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib

import pytest

import viewer

tk = pytest.importorskip("tkinter")


@pytest.fixture
def tab():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    root.withdraw()
    widget = viewer.CSVTab(root)
    widget.pack(fill="both", expand=True)
    widget.header = ["name", "n"]
    widget.rows = [["c", "10"], ["a", "9"], ["d", "100"], ["b", "x"], ["e", ""]]
    widget._populate_tree()
    yield widget
    with contextlib.suppress(tk.TclError):
        root.destroy()


def shown(tab, col=0):
    return [tab._rows_by_iid[i][col] for i in tab.tree.get_children("")]


def test_sorting_orders_the_rows_on_screen(tab):
    tab._sort_by("#1")

    assert shown(tab) == ["a", "b", "c", "d", "e"]


def test_numbers_sort_by_value_and_text_goes_after_them(tab):
    tab._sort_by("#2")

    assert shown(tab, 1) == ["9", "10", "100", "", "x"]


def test_the_second_click_reverses_the_order(tab):
    tab._sort_by("#1")
    tab._sort_by("#1")

    assert shown(tab) == ["e", "d", "c", "b", "a"]


def test_every_row_is_still_there_exactly_once(tab):
    before = set(tab.tree.get_children(""))

    tab._sort_by("#2")

    assert len(tab.tree.get_children("")) == 5
    assert set(tab.tree.get_children("")) == before


def test_the_stripes_follow_the_new_order(tab):
    tab._sort_by("#1")

    tags = [tab.tree.item(i, "tags")[0] for i in tab.tree.get_children("")]
    assert tags == ["evenrow", "oddrow", "evenrow", "oddrow", "evenrow"]


def test_the_header_shows_the_direction_of_the_sorted_column_only(tab):
    tab._sort_by("#1")

    assert tab.tree.heading("c0", "text") == "name ▲"
    assert tab.tree.heading("c1", "text") == "n"
