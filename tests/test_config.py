"""Tests for the persisted config file (zoom, dark mode, recent files)."""
import viewer


def _point_config_at(monkeypatch, tmp_path):
    config_dir = tmp_path / "CSVViewer"
    config_file = config_dir / "config.json"
    monkeypatch.setattr(viewer, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(viewer, "CONFIG_FILE", str(config_file))
    return config_dir, config_file


class TestLoadConfig:
    def test_missing_file_returns_empty_dict(self, monkeypatch, tmp_path):
        _point_config_at(monkeypatch, tmp_path)
        assert viewer.load_config() == {}

    def test_corrupted_json_returns_empty_dict(self, monkeypatch, tmp_path):
        config_dir, config_file = _point_config_at(monkeypatch, tmp_path)
        config_dir.mkdir(parents=True)
        config_file.write_text("{not valid json", encoding="utf-8")

        assert viewer.load_config() == {}

    def test_a_config_that_is_not_an_object_returns_empty_dict(self, monkeypatch, tmp_path):
        # valid JSON, but the app reads it with .get(): a list or a bare number
        # used to be returned as is, and then crashed the app at startup
        config_dir, config_file = _point_config_at(monkeypatch, tmp_path)
        config_dir.mkdir(parents=True)

        for text in ("[]", "[1, 2]", "42", '"text"', "null", "true"):
            config_file.write_text(text, encoding="utf-8")
            assert viewer.load_config() == {}, text

    def test_a_config_with_invalid_bytes_returns_empty_dict(self, monkeypatch, tmp_path):
        # not UTF-8 at all (a half-written or foreign file): UnicodeDecodeError
        # is not a JSONDecodeError, so it used to escape and stop the app
        config_dir, config_file = _point_config_at(monkeypatch, tmp_path)
        config_dir.mkdir(parents=True)
        config_file.write_bytes(b'{"zoom_pct": \xff\xfe}')

        assert viewer.load_config() == {}

    def test_an_empty_config_file_returns_empty_dict(self, monkeypatch, tmp_path):
        config_dir, config_file = _point_config_at(monkeypatch, tmp_path)
        config_dir.mkdir(parents=True)
        config_file.write_text("", encoding="utf-8")

        assert viewer.load_config() == {}


class TestSaveConfig:
    def test_round_trip(self, monkeypatch, tmp_path):
        _point_config_at(monkeypatch, tmp_path)
        data = {"zoom_pct": 150, "dark_mode": True, "recent_files": ["a.csv", "b.csv"]}

        viewer.save_config(data)

        assert viewer.load_config() == data

    def test_creates_config_dir_if_missing(self, monkeypatch, tmp_path):
        config_dir, _ = _point_config_at(monkeypatch, tmp_path)
        assert not config_dir.exists()

        viewer.save_config({"zoom_pct": 100})

        assert config_dir.exists()

    def test_does_not_raise_when_directory_creation_fails(self, monkeypatch, tmp_path):
        _point_config_at(monkeypatch, tmp_path)

        def boom(*args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(viewer.os, "makedirs", boom)

        # should be swallowed, not propagated
        viewer.save_config({"zoom_pct": 100})
