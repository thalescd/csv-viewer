"""Tests for tab teardown.

These need a display. On a headless runner without Xvfb they skip rather
than fail -- the CI job that gives them one is tracked separately.
"""
import contextlib

import pytest

import viewer

tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402  (must come after the importorskip guard)


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    r.withdraw()
    yield r
    with contextlib.suppress(tk.TclError):
        r.destroy()


class TestCloseNotebookTab:
    def test_the_widget_is_destroyed_not_just_unmapped(self, root):
        nb = ttk.Notebook(root)
        frame = ttk.Frame(nb)
        nb.add(frame, text="one")

        viewer.close_notebook_tab(nb, str(frame))

        # winfo_exists() is exactly what _reposition_separators tests before
        # rescheduling itself, so a live widget here means a 400 ms timer that
        # never stops -- and a `rows` list that is never freed.
        assert not frame.winfo_exists()

    def test_the_tab_is_removed_from_the_notebook(self, root):
        nb = ttk.Notebook(root)
        keep = ttk.Frame(nb)
        drop = ttk.Frame(nb)
        nb.add(keep, text="keep")
        nb.add(drop, text="drop")

        viewer.close_notebook_tab(nb, str(drop))

        assert nb.tabs() == (str(keep),)

    def test_forget_alone_would_leave_the_widget_alive(self, root):
        # pins the reason this helper exists: forget() only unmaps.
        nb = ttk.Notebook(root)
        frame = ttk.Frame(nb)
        nb.add(frame, text="one")

        nb.forget(frame)

        assert frame.winfo_exists()
        frame.destroy()

    def test_closing_an_unknown_tab_id_does_not_raise(self, root):
        nb = ttk.Notebook(root)
        frame = ttk.Frame(nb)
        nb.add(frame, text="one")
        viewer.close_notebook_tab(nb, str(frame))

        # closing twice is a no-op, not a TclError reaching the user
        viewer.close_notebook_tab(nb, str(frame))
