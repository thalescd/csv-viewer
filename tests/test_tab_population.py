"""Tests for what a tab shows right after a file is loaded.

The zebra stripes are set as each row is inserted, not in a second pass, so
these pin down that every row still gets the right one.

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
    widget.header = ["n"]
    yield widget
    with contextlib.suppress(tk.TclError):
        root.destroy()


def load_rows(tab, count):
    tab.rows = [[str(i)] for i in range(count)]
    tab._populate_tree()


def stripes(tab):
    return [tab.tree.item(iid, "tags") for iid in tab.tree.get_children("")]


def test_rows_alternate_even_and_odd_from_the_first(tab):
    load_rows(tab, 5)

    assert stripes(tab) == [("evenrow",), ("oddrow",), ("evenrow",), ("oddrow",), ("evenrow",)]


def test_every_row_has_exactly_one_stripe(tab):
    load_rows(tab, 101)

    assert all(len(tags) == 1 for tags in stripes(tab))


def test_a_reload_with_fewer_rows_starts_again_from_even(tab):
    load_rows(tab, 7)
    load_rows(tab, 3)

    assert stripes(tab) == [("evenrow",), ("oddrow",), ("evenrow",)]


def test_an_empty_file_has_no_rows_and_no_error(tab):
    load_rows(tab, 0)

    assert stripes(tab) == []


def test_the_stripe_colours_come_from_the_palette(tab):
    load_rows(tab, 2)
    palette = viewer.PALETTES["light"]

    assert str(tab.tree.tag_configure("evenrow", "background")) == palette["stripe_even"]
    assert str(tab.tree.tag_configure("oddrow", "background")) == palette["stripe_odd"]
