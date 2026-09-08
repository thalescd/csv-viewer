"""Tests for delimiter detection and CSV/TSV file reading."""
import pytest

import viewer


class TestSniffDelimiter:
    def test_detects_comma(self):
        sample = "a,b,c\n1,2,3\n4,5,6\n"
        assert viewer.sniff_delimiter(sample) == ","

    def test_detects_semicolon(self):
        sample = "a;b;c\n1;2;3\n4;5;6\n"
        assert viewer.sniff_delimiter(sample) == ";"

    def test_detects_tab(self):
        sample = "a\tb\tc\n1\t2\t3\n4\t5\t6\n"
        assert viewer.sniff_delimiter(sample) == "\t"

    def test_detects_pipe(self):
        sample = "a|b|c\n1|2|3\n4|5|6\n"
        assert viewer.sniff_delimiter(sample) == "|"

    def test_falls_back_when_undetectable(self):
        # no delimiter characters at all -> csv.Sniffer can't guess one
        sample = "abc\ndef\nghi\n"
        assert viewer.sniff_delimiter(sample, fallback_from_ext=";") == ";"

    def test_falls_back_to_comma_by_default(self):
        sample = "abc\ndef\nghi\n"
        assert viewer.sniff_delimiter(sample) == ","


class TestReadCsvFile:
    def test_basic_comma_csv(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("name,age\nAna,34\nBruno,28\n", encoding="utf-8")

        header, rows, delimiter, encoding = viewer.read_csv_file(str(p))

        assert header == ["name", "age"]
        assert rows == [["Ana", "34"], ["Bruno", "28"]]
        assert delimiter == ","
        assert encoding == "utf-8-sig"

    def test_tsv_extension_defaults_to_tab(self, tmp_path):
        p = tmp_path / "data.tsv"
        p.write_text("a\tb\n1\t2\n", encoding="utf-8")

        header, rows, delimiter, _ = viewer.read_csv_file(str(p))

        assert delimiter == "\t"
        assert header == ["a", "b"]
        assert rows == [["1", "2"]]

    def test_explicit_delimiter_overrides_detection(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a;b\n1;2\n", encoding="utf-8")

        header, _rows, delimiter, _ = viewer.read_csv_file(str(p), delimiter=";")

        assert delimiter == ";"
        assert header == ["a", "b"]

    def test_short_rows_are_padded(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b,c\n1,2\n", encoding="utf-8")

        header, rows, _, _ = viewer.read_csv_file(str(p))

        assert header == ["a", "b", "c"]
        assert rows == [["1", "2", ""]]

    def test_long_rows_are_truncated(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n1,2,3,4\n", encoding="utf-8")

        header, rows, _, _ = viewer.read_csv_file(str(p))

        assert header == ["a", "b"]
        assert rows == [["1", "2"]]

    def test_empty_file_returns_empty_header_and_rows(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")

        header, rows, _, _ = viewer.read_csv_file(str(p))

        assert header == []
        assert rows == []

    def test_missing_file_raises(self, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        with pytest.raises(FileNotFoundError):
            viewer.read_csv_file(str(missing))

    def test_falls_back_to_latin1_on_undecodable_bytes(self, tmp_path):
        p = tmp_path / "latin1.csv"
        # accented characters encoded as cp1252 are not valid utf-8 on their own
        content = "name,city\nAna,Brasília\n"
        p.write_bytes(content.encode("cp1252"))

        header, rows, _, encoding = viewer.read_csv_file(str(p))

        assert header == ["name", "city"]
        assert rows == [["Ana", "Brasília"]]
        assert encoding in ("cp1252", "latin-1")
