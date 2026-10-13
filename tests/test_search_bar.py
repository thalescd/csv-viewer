"""Tests for the text fields: Ctrl+A, Enter in the search box, the dark-mode cursor.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib
import time
import types

import pytest

import viewer

tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402  (must come after the importorskip guard)


@pytest.fixture
def tab():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    root.withdraw()
    widget = viewer.CSVTab(root)
    widget.pack(fill="both", expand=True)
    widget.header = ["id", "name"]
    widget.rows = [[str(i), f"cliente {i % 7}"] for i in range(300)]
    widget._populate_tree()
    yield widget
    with contextlib.suppress(tk.TclError):
        root.destroy()


def search_for(tab, text):
    tab._search_var.set(text)
    tab._run_search()


def hit_text(tab):
    row, _col = tab._selected_cell
    return tab.rows[row][1]


class TestSelectAll:
    def test_it_selects_the_whole_text_and_leaves_the_cursor_at_the_end(self, tab):
        entry = tab._search_entry
        entry.insert(0, "cliente 3")
        entry.icursor(3)

        result = viewer.select_all_text(types.SimpleNamespace(widget=entry))

        assert entry.selection_get() == "cliente 3"
        assert entry.index("insert") == len("cliente 3")
        assert result == "break"  # so Tk's own "go to line start" does not run after it

    def test_it_works_on_an_empty_field(self, tab):
        viewer.select_all_text(types.SimpleNamespace(widget=tab._search_entry))

        assert tab._search_entry.get() == ""

    @pytest.mark.parametrize("sequence", ["<Control-a>", "<Control-A>"])
    def test_the_search_box_delimiter_box_and_custom_field_all_have_it(self, tab, sequence):
        assert tab._search_entry.bind(sequence)
        assert tab.delim_combo.bind(sequence)
        custom = [w for w in tab.winfo_children()[0].winfo_children()
                  if isinstance(w, ttk.Entry) and w is not tab._search_entry]
        assert custom and all(w.bind(sequence) for w in custom)


class TestEnterInTheSearchBox:
    @pytest.mark.parametrize("key", ["Return", "KP_Enter"])
    def test_both_enter_keys_go_to_the_next_result_and_with_shift_to_the_previous(self, tab, key):
        assert tab._search_entry.bind(f"<{key}>")
        assert tab._search_entry.bind(f"<Shift-{key}>")

    def test_a_step_moves_to_the_next_result(self, tab):
        search_for(tab, "cliente 3")
        before = tab._search_index

        tab._search_step(1)

        assert tab._search_index == before + 1

    def test_enter_right_after_typing_steps_through_the_new_text_not_the_old(self, tab):
        search_for(tab, "cliente 3")
        tab._search_var.set("cliente 5")  # typed; the 200 ms wait has not passed
        assert tab._search_after_id is not None

        tab._search_step(1)

        assert hit_text(tab) == "cliente 5"
        assert tab._search_after_id is None

    def test_the_pending_search_does_not_start_over_afterwards(self, tab):
        search_for(tab, "cliente 3")
        tab._search_var.set("cliente 5")
        tab._search_step(1)
        index = tab._search_index

        time.sleep(0.35)  # past the 200 ms wait that used to reset it to the first hit
        tab.update()

        assert tab._search_index == index

    def test_enter_right_after_typing_lands_on_the_second_hit_like_a_find_box(self, tab):
        tab._search_var.set("cliente 5")

        tab._search_step(1)

        assert tab._search_index == 1

    def test_running_the_search_by_hand_cancels_a_timer_still_waiting(self, tab):
        # Ctrl+F on a box that still has text, or a reload, runs the search
        # directly; the timer left over would fire later and restart it
        tab._search_var.set("cliente 3")
        assert tab._search_after_id is not None

        tab._run_search()

        assert tab._search_after_id is None

    def test_a_step_with_nothing_found_does_nothing(self, tab):
        tab._search_var.set("no such text anywhere")

        tab._search_step(1)

        assert tab._search_matches == []
        assert tab._search_status_var.get() == "0 results"

    def test_a_step_with_an_empty_box_does_nothing(self, tab):
        tab._search_step(1)

        assert tab._search_matches == []


class TestDarkModeCursor:
    def cursor_colour(self, app, style):
        return str(ttk.Style(app).lookup(style, "insertcolor"))

    def test_the_text_cursor_is_light_in_dark_mode(self, app):
        app.dark_mode_var.set(True)
        app.toggle_theme()

        fg = viewer.PALETTES["dark"]["fg"]
        assert self.cursor_colour(app, "TEntry") == fg
        assert self.cursor_colour(app, "TCombobox") == fg

    def test_the_cursor_is_not_forced_in_light_mode(self, app):
        app.dark_mode_var.set(True)
        app.toggle_theme()
        app.dark_mode_var.set(False)
        app.toggle_theme()

        assert self.cursor_colour(app, "TEntry") != viewer.PALETTES["dark"]["fg"]
