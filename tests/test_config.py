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
