"""Tests that a mouse event over a link cell behaves as it does over any cell.

A URL cell is covered by a Label of its own, which receives the events over
that cell. Without help it ignored right-click, the wheel and the middle
button, so a column of links could not be copied from or scrolled over.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib

import pytest

import viewer

tk = pytest.importorskip("tkinter")

CONTROL = 0x4


class FakeMenu:
    """Stands in for the pop-up menu, which would grab the real display."""

    def __init__(self):
        self.labels = []
        self.popped_up = False

    def add_command(self, label, command):
        self.labels.append(label)

    def add_separator(self):
        pass

    def tk_popup(self, *_):
        self.popped_up = True


@pytest.fixture
def zooms():
    return []


@pytest.fixture
def tab(zooms):
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    root.geometry("600x300")
    widget = viewer.CSVTab(
        root, zoom_label_var=tk.StringVar(root),
        on_zoom_delta=zooms.append, on_zoom_reset=lambda: None,
    )
    widget.pack(fill="both", expand=True)
    widget.header = ["id", "site"]
    widget.rows = [[str(i), f"https://example.com/{i}"] for i in range(300)]
    widget._populate_tree()
    widget.after = lambda *a, **k: None  # the redraw loop is driven by hand
    root.update()
    widget._reposition_separators()
    root.update()
    yield widget
    with contextlib.suppress(tk.TclError):
        root.destroy()


@pytest.fixture
def label(tab):
    shown = [lb for lb in tab._link_labels if lb.winfo_manager()]
    assert shown, "the fixture should have link labels on screen"
    return shown[1]


@pytest.fixture
def menu(tab):
    fake = FakeMenu()
    tab._make_menu = lambda: fake
    return fake


def test_right_click_on_a_link_opens_the_cell_menu(tab, label, menu):
    label.event_generate("<Button-3>", x=10, y=5)
    tab.update()

    assert menu.popped_up
    assert menu.labels == ["Copy cell", "Copy column", "Copy row"]


def test_right_click_on_a_link_selects_that_link_cell(tab, label, menu):
    label.event_generate("<Button-3>", x=10, y=5)
    tab.update()

    row, col = tab._selected_cell
    assert col == "c1"
    assert tab.tree.set(row, "c1") == label.cget("text")


def test_the_wheel_scrolls_the_table_over_a_link_on_x11(tab, label):
    before = tab.tree.yview()[0]

    label.event_generate("<Button-5>", x=10, y=5)
    tab.update()

    assert tab.tree.yview()[0] > before


def test_the_wheel_scrolls_the_table_over_a_link_on_windows_and_macos(tab, label):
    before = tab.tree.yview()[0]

    label.event_generate("<MouseWheel>", x=10, y=5, delta=-120)
    tab.update()

    assert tab.tree.yview()[0] > before


def test_scrolling_over_a_link_goes_as_far_as_scrolling_over_a_plain_cell(tab, label):
    start = tab.tree.yview()[0]
    tab.tree.event_generate("<Button-5>", x=10, y=100)
    tab.update()
    plain = tab.tree.yview()[0] - start

    tab.tree.yview_moveto(start)
    tab.update()
    label.event_generate("<Button-5>", x=10, y=5)
    tab.update()

    assert tab.tree.yview()[0] - start == pytest.approx(plain)


def test_ctrl_wheel_over_a_link_zooms(tab, label, zooms):
    label.event_generate("<MouseWheel>", x=10, y=5, delta=120, state=CONTROL)
    tab.update()

    assert zooms == [10]


def test_the_middle_button_over_a_link_pans(tab, label):
    label.event_generate("<ButtonPress-2>", x=10, y=5)
    tab.update()
    assert tab._pan_active

    label.event_generate("<ButtonRelease-2>", x=10, y=5)
    tab.update()
    assert not tab._pan_active
