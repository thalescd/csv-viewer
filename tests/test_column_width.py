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


class TestWidestCandidates:
    """Only the longest distinct values of a column are worth measuring."""

    def test_returns_the_longest_first(self):
        assert viewer.widest_candidates(["a", "abc", "ab", "abcd"], count=2) == ["abcd", "abc"]

    def test_a_value_that_repeats_is_listed_once(self):
        assert viewer.widest_candidates(["Bage"] * 1000 + ["Pelotas"] * 1000, count=5) == ["Pelotas", "Bage"]

    def test_fewer_values_than_the_count_gives_them_all(self):
        assert sorted(viewer.widest_candidates(["a", "bb"], count=20)) == ["a", "bb"]

    def test_no_values_gives_nothing(self):
        assert viewer.widest_candidates([]) == []

    def test_accepts_any_iterable(self):
        assert viewer.widest_candidates((v for v in ["a", "abc"]), count=1) == ["abc"]

    def test_the_widest_value_is_always_among_them_wherever_it_sits(self):
        values = [f"v{i}" for i in range(5000)]
        values[3333] = "the widest by far, hidden in the middle"

        assert viewer.widest_candidates(values)[0] == "the widest by far, hidden in the middle"

    def test_the_default_count_is_the_module_constant(self):
        values = [str(i) * (i % 7 + 1) for i in range(500)]

        assert len(viewer.widest_candidates(values)) == viewer.AUTOSIZE_MEASURE_COUNT
