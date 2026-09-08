"""Tests for matching column names, which Ctrl+F searches alongside the data."""
import viewer

HEADER = ["name", "Age", "city", "annual_income"]


class TestHeaderMatchColumns:
    def test_exact_name(self):
        assert viewer.header_match_columns(HEADER, "city") == [2]

    def test_is_case_insensitive(self):
        assert viewer.header_match_columns(HEADER, "AGE") == [1]
        assert viewer.header_match_columns(HEADER, "age") == [1]

    def test_matches_part_of_a_name(self):
        assert viewer.header_match_columns(HEADER, "income") == [3]

    def test_returns_every_matching_column(self):
        # "n" appears in name, annual_income
        assert viewer.header_match_columns(HEADER, "n") == [0, 3]

    def test_no_match(self):
        assert viewer.header_match_columns(HEADER, "salary") == []

    def test_empty_header(self):
        assert viewer.header_match_columns([], "anything") == []

    def test_non_string_headers_do_not_blow_up(self):
        assert viewer.header_match_columns(["a", 2024, None], "2024") == [1]
