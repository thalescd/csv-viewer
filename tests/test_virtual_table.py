"""Tests for the virtual table: the widget holds only the rows on screen.

The tree keeps as many items as fit in the window and refills them as the user
scrolls; `_order` says which row of `rows` sits at each position, and `_top` is
the position of the first one shown. These pin down that what is on screen is
always the right slice, that scrolling stays inside the data, and that
selections, search and copies keep working on rows that are not on screen.

These need a display. On a headless runner without Xvfb they skip rather
than fail, like the other Tk tests here.
"""
import contextlib
import types

import pytest

import viewer

tk = pytest.importorskip("tkinter")

ROWS = 5000


@pytest.fixture
def tab():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"no display available: {exc}")
    root.geometry("800x400")  # shown, not withdrawn: a hidden window has no height to fit rows to
    widget = viewer.CSVTab(root)
    widget.pack(fill="both", expand=True)
    widget.header = ["id", "name", "site"]
    widget.rows = [[str(i), f"n{i}", f"https://x.com/{i}"] for i in range(ROWS)]
    widget._populate_tree()
    root.update()
    yield widget
    with contextlib.suppress(tk.TclError):
        root.destroy()


def shown_ids(tab):
    """The first column of the items now in the widget, top to bottom."""
    return [tab.tree.item(iid, "values")[0] for iid in tab._slots]


def key(name):
    return types.SimpleNamespace(keysym=name)


class TestWindowOfItems:
    def test_the_widget_holds_only_the_rows_that_fit(self, tab):
        items = len(tab.tree.get_children(""))

        assert tab._page_rows() <= items <= tab._page_rows() + 2
        assert items < 100 < ROWS

    def test_all_the_data_is_still_held(self, tab):
        assert len(tab.rows) == ROWS
        assert tab._order == list(range(ROWS))

    def test_the_items_show_the_rows_from_the_top(self, tab):
        assert shown_ids(tab)[:3] == ["0", "1", "2"]

    def test_a_file_shorter_than_the_screen_has_exactly_its_rows_and_no_blank_ones(self, tab):
        tab.rows = [[str(i), "x", "y"] for i in range(5)]
        tab._populate_tree()

        assert shown_ids(tab) == ["0", "1", "2", "3", "4"]

    def test_a_file_with_no_rows_is_fine_and_cannot_be_scrolled(self, tab):
        tab.rows = []
        tab._populate_tree()

        tab._scroll_rows(5)
        tab.scroll_to_fraction(0.5)

        assert tab._slots == []
        assert tab._top == 0

    def test_the_stripes_follow_the_position_in_the_file_not_the_slot(self, tab):
        tab._scroll_rows(1)

        assert tab.tree.item(tab._slots[0], "tags") == ("oddrow",)
        assert tab.tree.item(tab._slots[1], "tags") == ("evenrow",)


class TestScrolling:
    def test_the_wheel_moves_three_rows_a_notch(self, tab):
        tab.tree.event_generate("<MouseWheel>", x=50, y=100, delta=-120)
        tab.update()

        assert tab._top == 3
        assert shown_ids(tab)[0] == "3"

    def test_the_wheel_up_goes_back(self, tab):
        tab._scroll_to(100)
        tab.tree.event_generate("<MouseWheel>", x=50, y=100, delta=120)
        tab.update()

        assert tab._top == 97

    def test_shift_and_the_wheel_scroll_sideways_not_down(self, tab):
        tab.tree.event_generate("<MouseWheel>", x=50, y=100, delta=-120, state=0x1)
        tab.update()

        assert tab._top == 0

    def test_it_cannot_scroll_above_the_first_row(self, tab):
        tab._scroll_rows(-100)

        assert tab._top == 0

    def test_it_cannot_scroll_past_the_last_row(self, tab):
        tab._scroll_rows(10 ** 6)

        assert tab._top == ROWS - tab._page_rows()

    def test_at_the_end_the_last_row_is_the_last_one_on_screen(self, tab):
        tab.scroll_to_fraction(1.0)

        visible = shown_ids(tab)[: tab._page_rows()]
        assert visible[-1] == str(ROWS - 1)

    def test_the_scrollbar_can_jump(self, tab):
        tab._on_vscroll("moveto", "0.5")

        assert tab._top == ROWS // 2

    def test_the_scrollbar_arrows_scroll_a_row(self, tab):
        tab._on_vscroll("scroll", "3", "units")
        tab._on_vscroll("scroll", "-1", "units")

        assert tab._top == 2

    def test_clicking_the_scrollbar_trough_scrolls_a_page(self, tab):
        tab._on_vscroll("scroll", "1", "pages")

        assert tab._top == tab._page_rows()

    def test_the_scrollbar_thumb_shows_where_the_page_is(self, tab, monkeypatch):
        seen = []
        monkeypatch.setattr(tab, "_vsb_set", lambda first, last: seen.append((first, last)))
        tab._scroll_to(ROWS // 2)

        first, last = seen[-1]
        assert first == pytest.approx(0.5)
        assert last == pytest.approx(0.5 + tab._page_rows() / ROWS)

    def test_the_thumb_covers_everything_when_the_file_fits(self, tab, monkeypatch):
        seen = []
        tab.rows = [[str(i), "x", "y"] for i in range(5)]
        tab._populate_tree()
        monkeypatch.setattr(tab, "_vsb_set", lambda first, last: seen.append((first, last)))

        tab._update_vscroll()

        assert seen[-1] == (0.0, 1.0)


class TestKeyboard:
    @pytest.mark.parametrize("name", ["Up", "Down", "Prior", "Next", "Home", "End", "Control-Home", "Control-End"])
    def test_every_scroll_key_is_bound(self, tab, name):
        assert tab.tree.bind(f"<{name}>")

    def test_down_and_up_move_one_row(self, tab):
        tab._on_scroll_key(key("Down"))
        tab._on_scroll_key(key("Down"))
        tab._on_scroll_key(key("Up"))

        assert tab._top == 1

    def test_page_down_moves_a_page_less_one_row_and_page_up_comes_back(self, tab):
        page = tab._page_rows() - 1

        tab._on_scroll_key(key("Next"))
        assert tab._top == page
        tab._on_scroll_key(key("Prior"))
        assert tab._top == 0

    def test_end_and_home(self, tab):
        tab._on_scroll_key(key("End"))
        assert tab._top == ROWS - tab._page_rows()

        tab._on_scroll_key(key("Home"))
        assert tab._top == 0

    def test_a_key_press_is_not_passed_on_to_the_widgets_own_selection(self, tab):
        assert tab._on_scroll_key(key("Down")) == "break"


class TestSelection:
    def click(self, tab, row_on_screen):
        y = tab._header_height() + row_on_screen * tab._row_height() + 5
        tab.tree.event_generate("<ButtonPress-1>", x=30, y=y)
        tab.update()

    def test_a_click_selects_the_row_of_the_data_not_the_widget_item(self, tab):
        self.click(tab, 2)
        assert tab._selected_cell == (2, "c0")

        tab._scroll_to(1000)
        # a different row: the same spot twice in a row would count as a double click
        self.click(tab, 4)
        assert tab._selected_cell == (1004, "c0")

    def test_the_outline_leaves_with_a_row_that_scrolls_away_and_returns_with_it(self, tab):
        tab._selected_cell = (10, "c0")
        assert tab._cell_rect(10, "c0") is not None

        tab._scroll_to(1000)
        assert tab._cell_rect(10, "c0") is None

        tab._scroll_to(0)
        assert tab._cell_rect(10, "c0") is not None

    def test_the_outline_sits_on_the_selected_cell_after_scrolling(self, tab):
        tab._selected_cell = (40, "c1")

        tab._scroll_to(35)

        x, y, w, h = tab._cell_rect(40, "c1")
        assert (x, y, w, h) == tab.tree.bbox(tab._slots[5], "c1")

    def test_a_selected_row_stays_selected_through_a_sort(self, tab):
        tab._selected_cell = (7, "c0")

        tab._sort_by("#1")  # by id, as text-looking numbers: descending order flips
        tab._sort_by("#1")

        assert tab._selected_cell == (7, "c0")
        assert tab._position_of(7) == ROWS - 1 - 7

    def test_clicking_empty_space_selects_nothing(self, tab):
        tab.scroll_to_fraction(1.0)
        filler = tab._slots[-1]

        assert tab._row_of_iid(filler) is None


class TestCopyingWhatIsNotOnScreen:
    def test_copying_a_column_takes_every_row_in_screen_order(self, tab):
        tab._sort_by("#1")  # ascending: already the file order
        tab._sort_by("#1")  # descending

        values = tab._column_values("c0")

        assert len(values) == ROWS
        assert values[:3] == [str(ROWS - 1), str(ROWS - 2), str(ROWS - 3)]

    def test_copying_the_row_of_a_selected_cell_far_from_the_top(self, tab):
        tab._scroll_to(3000)
        tab._selected_cell = (3001, "c1")

        tab._copy_selected_row()

        assert tab.clipboard_get() == "3001\tn3001\thttps://x.com/3001"

    def test_copying_the_selected_cell_far_from_the_top(self, tab):
        tab._selected_cell = (4321, "c1")

        tab._copy_selected_cell()

        assert tab.clipboard_get() == "n4321"


class TestSearchAcrossTheWholeFile:
    def test_a_hit_far_away_is_scrolled_into_view_and_outlined(self, tab):
        tab._search_var.set("n4321")
        tab._run_search()
        tab.update()

        assert tab._search_matches == [(4321, "c1")]
        assert tab._top <= tab._position_of(4321) < tab._top + tab._page_rows()
        assert tab._cell_rect(4321, "c1") is not None

    def test_next_walks_down_the_file_and_wraps_to_the_start(self, tab):
        tab._search_var.set("n49")  # n49, n490-n499, n4900-n4999
        tab._run_search()
        first_hits = [tab._search_matches[tab._search_index]]
        for _ in range(len(tab._search_matches) - 1):
            tab._search_step(1)

        tab._search_step(1)

        assert tab._search_matches[tab._search_index] == first_hits[0]

    def test_a_hit_already_on_screen_does_not_move_the_view(self, tab):
        tab._scroll_to(100)
        tab._search_var.set("n105")
        tab._run_search()

        # n105 is on screen at top=100 (page of ~14 rows), so the first hit must not scroll
        assert tab._search_matches[0] == (105, "c1")
        assert tab._top == 100

    def test_the_hits_follow_a_sort_and_the_current_one_stays_selected(self, tab):
        tab._search_var.set("n4321")
        tab._run_search()
        before = tab._selected_cell

        tab._sort_by("#1")
        tab._sort_by("#1")

        assert tab._selected_cell == before == (4321, "c1")
        assert tab._cell_rect(*tab._selected_cell) is None or tab._top <= tab._position_of(4321)


class TestFollowsTheWindowAndTheZoom:
    def test_a_taller_window_gets_more_items_and_still_starts_at_the_same_row(self, tab):
        tab._scroll_to(500)
        before = len(tab._slots)

        tab.winfo_toplevel().geometry("800x800")
        tab.update()

        assert len(tab._slots) > before
        assert shown_ids(tab)[0] == "500"

    def test_a_shorter_window_gets_fewer_items(self, tab):
        before = len(tab._slots)

        tab.winfo_toplevel().geometry("800x250")
        tab.update()

        assert len(tab._slots) < before

    def test_enlarging_the_window_at_the_bottom_pulls_the_view_back_so_no_blank_page_shows(self, tab):
        tab.scroll_to_fraction(1.0)

        tab.winfo_toplevel().geometry("800x800")
        tab.update()

        assert tab._top == ROWS - tab._page_rows()
        assert shown_ids(tab)[tab._page_rows() - 1] == str(ROWS - 1)

    def test_a_reload_starts_again_from_the_top(self, tab, tmp_path):
        path = tmp_path / "f.csv"
        path.write_text("id,name,site\n" + "".join(f"{i},n{i},s\n" for i in range(300)), encoding="utf-8")
        tab.load(str(path))
        tab._scroll_to(200)

        tab.reload()

        assert tab._top == 0
        assert shown_ids(tab)[0] == "0"


def test_zooming_changes_how_many_items_fit(app, tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("id,name\n" + "".join(f"{i},n{i}\n" for i in range(2000)), encoding="utf-8")
    app.geometry("900x500")
    app.deiconify()
    app.update()
    app.open_file(str(path))
    app.update()
    (tab,) = [app.nametowidget(t) for t in app.notebook.tabs()]
    at_100 = len(tab._slots)

    app.apply_zoom(200)
    app.update()

    assert len(tab._slots) < at_100
