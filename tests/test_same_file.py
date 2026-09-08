"""Tests for path comparison, which decides whether a file is already open."""
import os

import pytest

import viewer


class TestSameFileKey:
    def test_identical_paths_match(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n", encoding="utf-8")

        assert viewer.same_file_key(str(p)) == viewer.same_file_key(str(p))

    def test_relative_and_absolute_match(self, tmp_path, monkeypatch):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        assert viewer.same_file_key("data.csv") == viewer.same_file_key(str(p))

    def test_redundant_segments_match(self, tmp_path):
        p = tmp_path / "sub" / "data.csv"
        p.parent.mkdir()
        p.write_text("a,b\n", encoding="utf-8")
        noisy = os.path.join(str(tmp_path), "sub", ".", "..", "sub", "data.csv")

        assert viewer.same_file_key(noisy) == viewer.same_file_key(str(p))

    def test_different_files_do_not_match(self, tmp_path):
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        a.write_text("x\n", encoding="utf-8")
        b.write_text("x\n", encoding="utf-8")

        assert viewer.same_file_key(str(a)) != viewer.same_file_key(str(b))

    @pytest.mark.skipif(os.name != "nt", reason="Windows paths are case-insensitive")
    def test_casing_is_ignored_on_windows(self, tmp_path):
        p = tmp_path / "Data.csv"
        p.write_text("a,b\n", encoding="utf-8")

        assert viewer.same_file_key(str(p)) == viewer.same_file_key(str(p).upper())

    @pytest.mark.skipif(os.name != "nt", reason="only Windows accepts both separators")
    def test_slash_direction_is_ignored_on_windows(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("a,b\n", encoding="utf-8")

        assert viewer.same_file_key(str(p)) == viewer.same_file_key(str(p).replace("\\", "/"))
