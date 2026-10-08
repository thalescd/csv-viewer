"""Tests for finding the rows on screen once the table has been scrolled.

Separator lines, link overlays and the column-border actions all measure from
the topmost drawn row. That lookup used to search only the first 200 rows, so
in any longer file they stopped working as soon as the user scrolled past
them.

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
    # not withdrawn: a hidden window has no geometry, so nothing is "drawn"
    root.geometry("600x300")
    widget = viewer.CSVTab(root)
    widget.pack(fill="both", expand=True)
    widget.header = ["a", "b"]
    widget.rows = [[str(i), "x"] for i in range(5000)]
    widget._populate_tree()
    root.update()
    yield widget
    with contextlib.suppress(tk.TclError):
        root.destroy()


def test_a_row_is_found_at_the_top(tab):
    assert tab._first_visible_item() == tab.tree.get_children("")[0]


def test_a_row_is_still_found_after_scrolling_far_past_the_first_200(tab):
    tab.tree.yview_moveto(0.5)
    tab.update()

    item = tab._first_visible_item()

    assert item is not None
    assert tab.tree.bbox(item)  # it really is on screen
    assert tab._rows_by_iid[item] not in tab.rows[:200]


def test_the_header_height_does_not_fall_back_to_a_guess_when_scrolled(tab):
    top = tab._header_height()
    tab.tree.yview_moveto(0.5)
    tab.update()

    assert tab._header_height() == top
