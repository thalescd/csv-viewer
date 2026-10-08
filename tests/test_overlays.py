"""Tests that the column separators and link labels land where the cells are.

They are positioned by adding up column widths and row heights, not by asking
the widget for every cell's bbox (which is slow in a long file). So the check
is against the widget's own bbox: whatever the table looks like, the overlays
must sit exactly on it.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib

import pytest

import viewer

tk = pytest.importorskip("tkinter")

ROW_COUNT = 400


@pytest.fixture
def tab():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    root.geometry("500x300")
    widget = viewer.CSVTab(root)
    widget.pack(fill="both", expand=True)
    widget.header = ["id", "site", "note", "doc"]
    widget.rows = [
        [str(i), f"https://example.com/{i}", "x" * (i % 9) * 4, f"www.example.org/{i}"]
        for i in range(ROW_COUNT)
    ]
    widget._populate_tree()
    widget.after = lambda *a, **k: None  # the loop is driven by hand below
    root.update()
    yield widget
    with contextlib.suppress(tk.TclError):
        root.destroy()


def redraw(tab):
    tab.update()
    tab._reposition_separators()
    tab.update()


def placed_labels(tab):
    labels = [lb for lb in tab._link_labels if lb.winfo_manager()]
    return {(int(lb.place_info()["x"]), int(lb.place_info()["y"])): lb for lb in labels}


def assert_overlays_sit_on_the_cells(tab):
    tree = tab.tree
    top = tab._first_visible_item()
    cols = tab._display_columns()

    # separators: the right edge of every column but the last
    expected_edges = []
    for cid in cols[:-1]:
        x, _y, w, _h = tree.bbox(top, cid)
        expected_edges.append(x + w)
    placed_edges = [int(f.place_info()["x"]) for f in tab._sep_frames if f.winfo_manager()]
    assert placed_edges == expected_edges

    # link labels: one per visible URL cell, on that cell's bbox
    labels = placed_labels(tab)
    link_cols = [c for c in cols if int(c[1:]) in tab._link_col_idxs]
    iid, drawn = top, 0
    while iid:
        bbox_row = tree.bbox(iid)
        if not bbox_row or bbox_row[1] > tree.winfo_height():
            break
        for cid in link_cols:
            x, y, w, h = tree.bbox(iid, cid)
            if x + w <= 0 or x >= tree.winfo_width():
                continue
            label = labels.get((x, y))
            assert label is not None, f"no label on {cid} of {iid} at {(x, y)}"
            assert (int(label.place_info()["width"]), int(label.place_info()["height"])) == (w, h)
            assert label.cget("text") == tree.set(iid, cid)
            drawn += 1
        iid = tree.next(iid)
    assert drawn == len(labels) > 0


def test_overlays_sit_on_the_cells_at_the_top(tab):
    redraw(tab)
    assert_overlays_sit_on_the_cells(tab)


def test_overlays_follow_a_vertical_scroll_far_past_the_first_rows(tab):
    tab.tree.yview_moveto(0.6)
    redraw(tab)
    assert_overlays_sit_on_the_cells(tab)


def test_overlays_follow_a_horizontal_scroll(tab):
    tab.tree.column("c2", width=600, stretch=False)
    tab.update()
    tab.tree.xview_moveto(0.5)
    redraw(tab)
    assert_overlays_sit_on_the_cells(tab)


def test_overlays_follow_reordered_columns(tab):
    tab.tree["displaycolumns"] = ["c3", "c0", "c2", "c1"]
    redraw(tab)
    assert_overlays_sit_on_the_cells(tab)


def test_overlays_follow_a_resized_column(tab):
    redraw(tab)
    tab.tree.column("c0", width=200, stretch=False)
    redraw(tab)
    assert_overlays_sit_on_the_cells(tab)


def test_the_header_height_is_measured_again_after_it_changes(tab):
    redraw(tab)
    before = tab._header_height()
    tab._header_y = before + 7  # a stale remembered height, as after a zoom
    redraw(tab)

    assert tab._header_height() == before
    assert_overlays_sit_on_the_cells(tab)


def test_the_link_font_is_built_once_until_the_font_changes(tab):
    redraw(tab)
    first = tab._link_label_font()
    redraw(tab)

    assert tab._link_label_font() is first
