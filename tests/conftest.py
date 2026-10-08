"""Fixtures shared by the tests that need the whole application.

They need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib

import pytest

import viewer

tk = pytest.importorskip("tkinter")


@pytest.fixture
def errors(monkeypatch):
    """Records error dialogs instead of opening them."""
    shown = []
    monkeypatch.setattr(viewer.messagebox, "showerror", lambda title, msg: shown.append((title, msg)))
    return shown


@pytest.fixture
def app(tmp_path, monkeypatch, errors):
    # the app writes its settings on every open: keep that out of the real file
    monkeypatch.setattr(viewer, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(viewer, "CONFIG_FILE", str(tmp_path / "config" / "config.json"))
    try:
        a = viewer.CSVViewerApp()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    a.withdraw()
    yield a
    with contextlib.suppress(tk.TclError):
        a.destroy()
