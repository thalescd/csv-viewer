"""Tests for the text a multi-value copy puts on the clipboard."""
import viewer


class TestClipboardField:
    def test_a_plain_value_goes_through_untouched(self):
        assert viewer.clipboard_field("Bage") == "Bage"

    def test_a_newline_is_quoted_so_it_does_not_read_as_a_new_row(self):
        assert viewer.clipboard_field("rua A\nsala 2") == '"rua A\nsala 2"'

    def test_a_tab_is_quoted_so_it_does_not_read_as_a_new_column(self):
        assert viewer.clipboard_field("a\tb") == '"a\tb"'

    def test_inner_quotes_are_doubled_csv_style(self):
        assert viewer.clipboard_field('say "hi"') == '"say ""hi"""'

    def test_none_becomes_empty(self):
        assert viewer.clipboard_field(None) == ""

    def test_non_strings_are_stringified(self):
        assert viewer.clipboard_field(2024) == "2024"


class TestClipboardColumn:
    def test_one_value_per_line(self):
        assert viewer.clipboard_column(["a", "b", "c"]) == "a\nb\nc"

    def test_the_header_goes_on_top_when_asked(self):
        assert viewer.clipboard_column(["a", "b"], header="letra") == "letra\na\nb"

    def test_an_empty_header_name_is_still_a_line(self):
        # a CSV with an unnamed column still pastes with the blank cell on top,
        # otherwise the values would land one row above where they belong
        assert viewer.clipboard_column(["a"], header="") == "\na"

    def test_no_header_means_values_only(self):
        assert viewer.clipboard_column(["a"]) == "a"

    def test_empty_column(self):
        assert viewer.clipboard_column([]) == ""

    def test_a_value_with_a_newline_stays_one_field(self):
        assert viewer.clipboard_column(["a\nb", "c"]) == '"a\nb"\nc'


class TestClipboardRow:
    def test_fields_are_tab_separated(self):
        assert viewer.clipboard_row(["ana", "30", "bage"]) == "ana\t30\tbage"

    def test_empty_row(self):
        assert viewer.clipboard_row([]) == ""
