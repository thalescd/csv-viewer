"""Tests that measured column widths follow the zoom.

Widths are measured from the real fonts and cached per tab. A zoom change
makes the text a different size, so a width measured before it is wrong.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import pytest

tk = pytest.importorskip("tkinter")

TEXT = "a fairly long value, long enough to need real room"


@pytest.fixture
def tab(app, tmp_path):
    path = tmp_path / "wide.csv"
    path.write_text(f"id,note\n1,{TEXT}\n", encoding="utf-8")
    app.open_file(str(path))
    (opened,) = [app.nametowidget(t) for t in app.notebook.tabs()]
    return opened


def test_a_double_click_fit_after_zooming_uses_the_new_size(app, tab):
    tab._autosize_column("c1")
    at_100 = tab.tree.column("c1", "width")

    app.apply_zoom(200)
    tab._autosize_column("c1")

    assert tab.tree.column("c1", "width") > at_100


def test_turning_fitting_on_after_zooming_uses_the_new_size(app, tab):
    tab._autosize_column("c1")  # measures every column, at 100%
    at_100 = tab._content_widths["c1"]
    app.apply_zoom(200)

    tab.set_fit_columns(True)

    assert tab.tree.column("c1", "width") > at_100


def test_zooming_with_fitting_on_still_refits_straight_away(app, tab):
    tab.set_fit_columns(True)
    at_100 = tab.tree.column("c1", "width")

    app.apply_zoom(200)

    assert tab.tree.column("c1", "width") > at_100
