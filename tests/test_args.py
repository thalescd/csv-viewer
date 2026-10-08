"""Tests for reading the command line."""
import os

import viewer


def test_a_relative_path_becomes_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    _, files = viewer.parse_args(["data.csv"])

    assert files == [str(tmp_path / "data.csv")]


def test_an_absolute_path_is_left_alone(tmp_path):
    path = str(tmp_path / "data.csv")

    assert viewer.parse_args([path])[1] == [path]


def test_several_files_keep_their_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    _, files = viewer.parse_args(["b.csv", "a.tsv"])

    assert [os.path.basename(f) for f in files] == ["b.csv", "a.tsv"]


def test_new_window_is_a_flag_not_a_file():
    force, files = viewer.parse_args(["--new-window"])

    assert force is True
    assert files == []


def test_no_arguments_means_no_files_and_the_shared_window():
    assert viewer.parse_args([]) == (False, [])
