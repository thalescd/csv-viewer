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


class TestQuotedFields:
    """Quoting rules the csv module knows about but a line-splitter does not."""

    def test_newline_inside_quoted_field_is_preserved(self, tmp_path):
        p = tmp_path / "multiline.csv"
        # bytes, not write_text: on Windows write_text would turn every \n into
        # \r\n and the test would be asserting about the wrong file.
        p.write_bytes(b'id,note\n1,"line 1\nline 2"\n')

        header, rows, _, _ = viewer.read_csv_file(str(p))

        assert header == ["id", "note"]
        assert rows == [["1", "line 1\nline 2"]]

    def test_crlf_inside_quoted_field_is_preserved(self, tmp_path):
        p = tmp_path / "crlf.csv"
        p.write_bytes(b'id,note\r\n1,"line 1\r\nline 2"\r\n')

        _header, rows, _, _ = viewer.read_csv_file(str(p))

        # one record, and the embedded break survives as a single newline
        assert len(rows) == 1
        assert rows[0][1].replace("\r\n", "\n") == "line 1\nline 2"

    def test_delimiter_inside_quoted_field_is_not_a_split(self, tmp_path):
        p = tmp_path / "embedded_delim.csv"
        p.write_text('id,city\n1,"Passo Fundo, RS"\n', encoding="utf-8")

        _header, rows, _, _ = viewer.read_csv_file(str(p), delimiter=",")

        assert rows == [["1", "Passo Fundo, RS"]]

    def test_escaped_double_quotes_are_unescaped(self, tmp_path):
        p = tmp_path / "escaped.csv"
        p.write_text('id,note\n1,"say ""hi"" now"\n', encoding="utf-8")

        _header, rows, _, _ = viewer.read_csv_file(str(p), delimiter=",")

        assert rows == [["1", 'say "hi" now']]

    # str.splitlines() breaks on these code points; the CSV format does not.
    @pytest.mark.parametrize("code", [0x0B, 0x0C, 0x85, 0x2028, 0x2029])
    def test_unicode_line_boundaries_do_not_split_records(self, tmp_path, code):
        char = chr(code)
        p = tmp_path / "boundaries.csv"
        p.write_bytes(f"id,note\n1,before{char}after\n".encode())

        _header, rows, _, _ = viewer.read_csv_file(str(p), delimiter=",")

        assert rows == [["1", f"before{char}after"]]


class TestEncodingDetection:
    """BOM-carrying files, which the cp1252/latin-1 chain silently mis-decodes."""

    def test_utf8_bom_is_stripped(self, tmp_path):
        p = tmp_path / "utf8bom.csv"
        p.write_bytes("name,city\nAna,Passo Fundo\n".encode("utf-8-sig"))

        header, rows, _, encoding = viewer.read_csv_file(str(p))

        assert header == ["name", "city"]
        assert rows == [["Ana", "Passo Fundo"]]
        assert encoding == "utf-8-sig"

    def test_utf16_le_with_bom(self, tmp_path):
        # what PowerShell 5.1 `Out-File` / `>` and Excel "Unicode Text" produce
        p = tmp_path / "utf16le.csv"
        p.write_bytes(b"\xff\xfe" + "name,city\nAna,Passo Fundo\n".encode("utf-16-le"))

        header, rows, _, encoding = viewer.read_csv_file(str(p))

        assert header == ["name", "city"]
        assert rows == [["Ana", "Passo Fundo"]]
        assert encoding.startswith("utf-16")

    def test_utf16_be_with_bom(self, tmp_path):
        p = tmp_path / "utf16be.csv"
        p.write_bytes(b"\xfe\xff" + "name,city\nAna,Passo Fundo\n".encode("utf-16-be"))

        header, rows, _, encoding = viewer.read_csv_file(str(p))

        assert header == ["name", "city"]
        assert rows == [["Ana", "Passo Fundo"]]
        assert encoding.startswith("utf-16")

    def test_utf16_tab_separated_keeps_tab_delimiter(self, tmp_path):
        p = tmp_path / "utf16.tsv"
        p.write_bytes("name\tcity\nAna\tPasso Fundo\n".encode("utf-16"))

        header, rows, delimiter, _ = viewer.read_csv_file(str(p))

        assert delimiter == "\t"
        assert header == ["name", "city"]
        assert rows == [["Ana", "Passo Fundo"]]

    def test_bomless_utf16_is_refused_with_a_readable_message(self, tmp_path):
        # no BOM to key on: we cannot decode it, but the dialog must not show
        # the raw `_csv.Error: line contains NUL`.
        p = tmp_path / "bomless.csv"
        p.write_bytes("name,city\nAna,Passo Fundo\n".encode("utf-16-le"))

        with pytest.raises(OSError) as excinfo:
            viewer.read_csv_file(str(p))

        message = str(excinfo.value)
        assert "utf-16" in message.lower()
        assert "NUL" not in message
