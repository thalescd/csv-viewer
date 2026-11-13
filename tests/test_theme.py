"""Tests for the light/dark theme on the menus."""
import viewer


def set_dark(app, dark):
    app.dark_mode_var.set(dark)
    app.toggle_theme()


def check_mark_colour(menu):
    return str(menu.cget("selectcolor"))


def test_menu_check_marks_are_light_in_dark_mode(app):
    # the check mark of "Dark Mode", "Fit Columns..." was dark on the dark menu
    set_dark(app, True)
    for menu in (app._view_menu, app._help_menu):
        assert check_mark_colour(menu) == viewer.PALETTES["dark"]["menu_fg"]


def test_light_mode_puts_the_native_check_mark_back(app):
    native = check_mark_colour(app._view_menu)
    set_dark(app, True)
    set_dark(app, False)
    assert check_mark_colour(app._view_menu) == native


def test_dark_menus_have_an_edge_on_every_side(app):
    # the default raised edge draws bottom/right in a shade darker than the
    # menu, which disappeared on the dark window (X11)
    set_dark(app, True)
    for menu in (app._file_menu, app._view_menu, app._help_menu, app._recent_menu):
        assert str(menu.cget("relief")) == "ridge"


def test_light_mode_puts_the_native_edge_back(app):
    native = str(app._file_menu.cget("relief")), str(app._file_menu.cget("borderwidth"))
    set_dark(app, True)
    set_dark(app, False)
    assert (str(app._file_menu.cget("relief")), str(app._file_menu.cget("borderwidth"))) == native
