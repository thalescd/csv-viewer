"""Tests for the column ordering key."""
import pytest

import viewer


def ordered(values, reverse=False):
    return sorted(values, key=viewer.cell_sort_key, reverse=reverse)


class TestCellSortKey:
    def test_numbers_sort_numerically_not_as_text(self):
        assert ordered(["10", "9", "100", "2"]) == ["2", "9", "10", "100"]

    def test_negatives_and_decimals(self):
        assert ordered(["1.5", "-2", "0", "10"]) == ["-2", "0", "1.5", "10"]

    def test_text_sorts_case_insensitively_after_numbers(self):
        assert ordered(["banana", "3", "Apple", "1"]) == ["1", "3", "Apple", "banana"]

    def test_empty_strings_sort_with_the_text(self):
        assert ordered(["2", "", "1"]) == ["1", "2", ""]

    @pytest.mark.parametrize(
        "values",
        [
            ["3", "NaN", "1", "2"],
            ["3", "1", "NaN", "2"],
            ["NaN", "3", "1", "2"],
            ["3", "1", "2", "NaN"],
        ],
    )
    def test_nan_does_not_depend_on_its_position_in_the_input(self, values):
        # float("NaN") parses, and NaN compares false against everything --
        # including itself -- so in the numeric branch list.sort() produced an
        # order that varied with where the NaN happened to sit.
        assert ordered(values) == ["1", "2", "3", "NaN"]

    @pytest.mark.parametrize("literal", ["NaN", "nan", "-nan", "+NAN"])
    def test_every_spelling_of_nan_is_treated_as_text(self, literal):
        assert ordered(["2", literal, "1"]) == ["1", "2", literal]

    @pytest.mark.parametrize("literal", ["inf", "-inf", "Infinity", "-Infinity"])
    def test_infinities_are_treated_as_text(self, literal):
        # not finite, so out of the numeric branch: they sort stably as text
        # rather than as unbounded values that swallow the ends of the column.
        result = ordered(["5", literal, "10"])
        assert result[:2] == ["5", "10"]
        assert result[2] == literal

    def test_sorting_is_a_total_order_so_reverse_is_the_mirror(self):
        values = ["3", "NaN", "1", "inf", "2", "apple"]
        assert ordered(values, reverse=True) == list(reversed(ordered(values)))

    def test_mixed_column_is_deterministic_across_input_permutations(self):
        values = ["10", "NaN", "banana", "-3", "inf", "", "2.5"]
        first = ordered(values)
        assert ordered(list(reversed(values))) == first
        assert ordered(sorted(values)) == first
