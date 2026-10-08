"""Tests for the bits that differ between Windows and everything else."""
import os

import viewer


class TestWheelDirection:
    """Windows/macOS send <MouseWheel> with a signed delta; X11 has no such
    event and reports the wheel as presses of button 4 (up) and 5 (down)."""

    def test_x11_button_4_scrolls_up(self):
        assert viewer.wheel_direction(4, 0) == 1

    def test_x11_button_5_scrolls_down(self):
        assert viewer.wheel_direction(5, 0) == -1

    def test_positive_delta_scrolls_up(self):
        assert viewer.wheel_direction("??", 120) == 1

    def test_negative_delta_scrolls_down(self):
        assert viewer.wheel_direction("??", -120) == -1


class TestConfigDir:
    def test_windows_uses_appdata(self, monkeypatch):
        monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")
        assert viewer._config_dir().endswith("CSVViewer")
        assert "AppData" in viewer._config_dir()

    def test_elsewhere_honours_xdg_config_home(self, monkeypatch):
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", "/home/me/.config")
        # built with os.path.join, like the code: the separator is the platform's
        assert viewer._config_dir() == os.path.join("/home/me/.config", "CSVViewer")

    def test_falls_back_to_dot_config_in_the_home_dir(self, monkeypatch):
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", "/home/me")
        monkeypatch.setenv("USERPROFILE", "/home/me")  # what "~" means on Windows
        assert viewer._config_dir() == os.path.join("/home/me", ".config", "CSVViewer")
