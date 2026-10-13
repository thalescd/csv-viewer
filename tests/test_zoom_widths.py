"""Tests that measured column widths follow the zoom.

Widths are measured from the real fonts and cached per tab. A zoom change
makes the text a different size, so a width measured before it is wrong.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import pytest

import viewer

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


class FakeFont:
    """Counts measure() calls; a text is as wide as it is long (7 px a character)."""

    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def measure(self, text):
        FakeFont.calls += 1
        return 7 * len(text)


class TestMeasuringIsBounded:
    """Each font.measure() costs ~0.7 ms on some systems, so a column must not cost one per row."""

    ROWS = 5000

    @pytest.fixture
    def big_tab(self, tab, monkeypatch):
        tab.header = ["id", "note", "city"]
        tab.rows = [[str(i), f"note {i}", ["Bage", "Pelotas", "Caxias"][i % 3]] for i in range(self.ROWS)]
        tab.rows[1500][1] = "the widest value, a long way down the sample " * 2
        FakeFont.calls = 0
        monkeypatch.setattr(viewer.tkfont, "Font", FakeFont)
        return tab

    def test_the_number_of_measure_calls_does_not_grow_with_the_rows(self, big_tab):
        big_tab._measure_content_widths()

        assert FakeFont.calls <= len(big_tab.header) * (1 + viewer.AUTOSIZE_MEASURE_COUNT)

    def test_the_width_still_comes_from_the_widest_value(self, big_tab):
        big_tab._measure_content_widths()

        widest = 7 * len(big_tab.rows[1500][1])
        assert big_tab._content_widths["c1"] == viewer.fitted_column_width([widest])

    def test_the_result_matches_measuring_every_value(self, big_tab):
        sample = big_tab.rows[: viewer.AUTOSIZE_SAMPLE_LIMIT]
        heading = 7 * len("note")
        every_value = viewer.fitted_column_width([heading] + [7 * len(r[1]) for r in sample])

        big_tab._measure_content_widths()

        assert big_tab._content_widths["c1"] == every_value

    def test_a_widest_value_past_the_sample_is_left_out_as_documented(self, big_tab):
        big_tab.rows[viewer.AUTOSIZE_SAMPLE_LIMIT + 10][0] = "x" * 200

        big_tab._measure_content_widths()

        assert big_tab._content_widths["c0"] < viewer.fitted_column_width([7 * 200])
