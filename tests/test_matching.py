"""Tests for the in-memory cell scan behind Ctrl+F."""
import viewer


class TestCellsContaining:
    def test_finds_a_substring_anywhere_in_the_cell(self):
        rows = [["alpha", "beta"], ["gamma", "zeta"]]

        assert viewer.cells_containing(rows, "et", 2) == [(0, 1), (1, 1)]

    def test_is_case_insensitive_both_ways(self):
        rows = [["Passo Fundo"], ["PASSO FUNDO"], ["passo fundo"]]

        assert viewer.cells_containing(rows, "PaSsO", 1) == [(0, 0), (1, 0), (2, 0)]

    def test_results_come_out_in_row_then_column_order(self):
        rows = [["x", "x"], ["x", "x"]]

        assert viewer.cells_containing(rows, "x", 2) == [(0, 0), (0, 1), (1, 0), (1, 1)]

    def test_columns_past_ncols_are_ignored(self):
        # displaycolumns is what the user sees; a longer row is not searchable
        rows = [["a", "b", "hit"]]

        assert viewer.cells_containing(rows, "hit", 2) == []

    def test_short_rows_do_not_raise(self):
        rows = [["a"], ["a", "b"], []]

        assert viewer.cells_containing(rows, "b", 2) == [(1, 1)]

    def test_no_match_returns_empty(self):
        assert viewer.cells_containing([["a"], ["b"]], "zzz", 1) == []

    def test_empty_query_matches_every_scanned_cell(self):
        # _run_search never calls this with an empty query, but the function
        # should not be the thing that decides that.
        rows = [["a", "b"]]

        assert viewer.cells_containing(rows, "", 2) == [(0, 0), (0, 1)]

    def test_positions_refer_to_the_sequence_given_not_to_the_file(self):
        # the GUI passes rows in the tree's current display order, so that
        # "next result" walks down the screen rather than down the file
        file_order = [["alpha"], ["zzz"], ["beta"]]
        display_order = [["beta"], ["alpha"], ["zzz"]]

        assert viewer.cells_containing(file_order, "eta", 1) == [(2, 0)]
        assert viewer.cells_containing(display_order, "eta", 1) == [(0, 0)]
