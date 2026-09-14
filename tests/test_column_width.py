"""Tests for the column width policy used when fitting columns to the window."""
import viewer


class TestFittedColumnWidth:
    def test_adds_padding_to_the_widest_text(self):
        assert viewer.fitted_column_width([100, 180, 120], padding=20,
                                          minimum=50, maximum=400) == 200

    def test_never_goes_below_the_minimum(self):
        assert viewer.fitted_column_width([10], padding=20, minimum=60, maximum=400) == 60

    def test_never_goes_above_the_maximum(self):
        # a long free-text column would otherwise become unshrinkable, since
        # the fitted width is also used as the column's minwidth
        assert viewer.fitted_column_width([5000], padding=20, minimum=60, maximum=400) == 400

    def test_empty_column_falls_back_to_the_minimum(self):
        assert viewer.fitted_column_width([], padding=20, minimum=60, maximum=400) == 60

    def test_minimum_wins_over_a_smaller_maximum(self):
        # nonsensical config, but it must not return something below the floor
        assert viewer.fitted_column_width([100], padding=0, minimum=80, maximum=50) == 80

    def test_uses_the_module_defaults(self):
        expected = min(300 + viewer.COLUMN_PADDING, viewer.AUTOFIT_MAX_WIDTH)
        assert viewer.fitted_column_width([300]) == expected
