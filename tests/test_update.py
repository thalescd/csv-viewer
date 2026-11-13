"""Tests for the update check: version parsing, the GitHub reply, and what the app shows."""
import io
import sys
import threading
import time
from tkinter import ttk

import pytest

import viewer


class TestParseVersion:
    @pytest.mark.parametrize("text, expected", [
        ("0.2.0", (0, 2, 0)),
        ("v1.10.3", (1, 10, 3)),
        (" v2.0.0\n", (2, 0, 0)),
    ])
    def test_valid(self, text, expected):
        assert viewer.parse_version(text) == expected

    @pytest.mark.parametrize("text", ["", "1.2", "v1.2.3-beta", "1.2.3.4", "latest", None, 3])
    def test_invalid(self, text):
        assert viewer.parse_version(text) is None

    def test_compares_numerically_not_as_text(self):
        assert viewer.parse_version("0.10.0") > viewer.parse_version("0.9.0")

    def test_the_apps_own_version_parses(self):
        assert viewer.parse_version(viewer.__version__) is not None


class TestParseRelease:
    def test_valid_reply(self):
        release = viewer.parse_release({"tag_name": "v0.3.0", "body": "  Faster.  "})
        assert release == {"version": (0, 3, 0), "tag": "v0.3.0", "notes": "Faster."}

    def test_missing_notes(self):
        assert viewer.parse_release({"tag_name": "v0.3.0", "body": None})["notes"] == ""

    def test_compare_link_is_dropped(self):
        body = "- Faster\n\n**Full Changelog**: https://github.com/x/y/compare/v0.2.0...v0.3.0"
        assert viewer.parse_release({"tag_name": "v0.3.0", "body": body})["notes"] == "- Faster"

    def test_long_notes_are_cut(self):
        notes = viewer.parse_release({"tag_name": "v0.3.0", "body": "x" * 5000})["notes"]
        assert len(notes) <= viewer.RELEASE_NOTES_MAX_CHARS + 3
        assert notes.endswith("...")

    @pytest.mark.parametrize("data", [
        {}, {"tag_name": "nightly"}, {"tag_name": "v1.0.0/../../evil"}, {"tag_name": 1},
        [], "v1.0.0", None,
    ])
    def test_rejects_anything_else(self, data):
        # the tag ends up in the URL opened in the browser, so it has to be a bare version
        with pytest.raises(ValueError):
            viewer.parse_release(data)


def test_fetch_reads_the_api_reply(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        return io.BytesIO(b'{"tag_name": "v9.0.0", "body": "notes"}')

    monkeypatch.setattr(viewer.urllib.request, "urlopen", fake_urlopen)
    assert viewer.fetch_latest_release()["version"] == (9, 0, 0)
    assert seen["url"] == viewer.LATEST_RELEASE_API


class TestUpdateCheckDue:
    NOW = 1_000_000_000.0

    @pytest.mark.parametrize("last", [None, "yesterday", True, [1]])
    def test_missing_or_garbled_means_never_checked(self, last):
        assert viewer.update_check_due(last, self.NOW)

    def test_checked_recently(self):
        assert not viewer.update_check_due(self.NOW - 3600, self.NOW)

    def test_checked_over_a_day_ago(self):
        assert viewer.update_check_due(self.NOW - viewer.UPDATE_CHECK_INTERVAL, self.NOW)

    def test_timestamp_in_the_future(self):
        # the clock was moved back: checking again beats waiting for it to catch up
        assert viewer.update_check_due(self.NOW + 3600, self.NOW)


# ---------- the app (needs a display; see conftest) ----------

NEWER = {"version": (99, 0, 0), "tag": "v99.0.0", "notes": "Lots."}
SAME = {"version": viewer.parse_version(viewer.__version__), "tag": "v" + viewer.__version__, "notes": ""}


@pytest.fixture
def infos(monkeypatch):
    shown = []
    monkeypatch.setattr(viewer.messagebox, "showinfo", lambda title, msg: shown.append((title, msg)))
    return shown


def last_menubar_label(app):
    return app._menubar.entrycget("end", "label")


def find_button(widget, text):
    for child in widget.winfo_children():
        if isinstance(child, ttk.Button) and child.cget("text") == text:
            return child
        found = find_button(child, text)
        if found is not None:
            return found
    return None


def test_help_menu_has_the_commands(app):
    labels = [app._help_menu.entrycget(i, "label") for i in range(app._help_menu.index("end") + 1)
              if app._help_menu.type(i) != "separator"]
    assert labels == ["Check for Updates...", "Check for Updates Automatically", "About"]


def test_manual_check_when_up_to_date(app, infos):
    app._on_update_result({"release": SAME}, manual=True)
    assert infos and "latest version" in infos[0][1]
    assert app._update_offer is None


def test_automatic_check_up_to_date_stays_quiet(app, infos):
    app._on_update_result({"release": SAME}, manual=False)
    assert infos == []
    assert app._config["update_last_check"] <= time.time()


def test_automatic_check_finds_a_newer_release(app):
    menu_size = app._menubar.index("end")
    app._on_update_result({"release": NEWER}, manual=False)
    assert last_menubar_label(app) == "Update Available (v99.0.0)"
    # a second find replaces the entry instead of stacking another
    app._on_update_result({"release": NEWER}, manual=False)
    assert app._menubar.index("end") == menu_size + 1


def test_skipped_release_is_not_offered_again_automatically(app, infos):
    app._config["skipped_update"] = "v99.0.0"
    app._on_update_result({"release": NEWER}, manual=False)
    assert app._update_offer is None


def test_skipped_release_still_shows_when_asked(app):
    app._config["skipped_update"] = "v99.0.0"
    app._on_update_result({"release": NEWER}, manual=True)
    assert app._update_offer == NEWER


def test_skip_button_withdraws_the_offer(app):
    menu_size = app._menubar.index("end")
    app._offer_update(NEWER)
    dialog = app._show_update_dialog()
    find_button(dialog, "Skip This Version").invoke()
    assert app._update_offer is None
    assert app._menubar.index("end") == menu_size
    assert viewer.load_config()["skipped_update"] == "v99.0.0"


def test_download_button_opens_the_release_page(app, monkeypatch):
    opened = []
    monkeypatch.setattr(viewer.webbrowser, "open", opened.append)
    app._offer_update(NEWER)
    find_button(app._show_update_dialog(), "Download").invoke()
    assert opened == [f"{viewer.RELEASES_URL}/tag/v99.0.0"]


def test_failed_manual_check_says_so(app, errors):
    app._on_update_result({"error": OSError("offline")}, manual=True)
    assert errors and "offline" in errors[0][1]


def test_failed_automatic_check_is_silent_and_retried_next_launch(app, errors):
    app._on_update_result({"error": OSError("offline")}, manual=False)
    assert errors == []
    assert "update_last_check" not in app._config


def test_check_runs_in_the_background_and_reports(app, monkeypatch):
    monkeypatch.setattr(viewer, "fetch_latest_release", lambda: NEWER)
    app.check_for_updates()
    deadline = time.time() + 5
    while app._update_check_running and time.time() < deadline:
        app.update()
        time.sleep(0.01)
    assert app._update_offer == NEWER


def wait_for_check(app, timeout=5):
    deadline = time.time() + timeout
    while app._update_check_running and time.time() < deadline:
        app.update()
        time.sleep(0.01)


def offline():
    raise OSError("no network")


def test_automatic_check_offline_is_silent(app, monkeypatch, errors, infos):
    monkeypatch.setattr(viewer, "fetch_latest_release", offline)
    app.check_for_updates()
    wait_for_check(app)
    assert not app._update_check_running
    assert errors == [] and infos == []
    assert app._update_offer is None


def test_manual_check_offline_reports_the_error(app, monkeypatch, errors):
    monkeypatch.setattr(viewer, "fetch_latest_release", offline)
    app.check_for_updates(manual=True)
    wait_for_check(app)
    assert errors and "no network" in errors[0][1]


def test_a_hanging_connection_does_not_freeze_the_window(app, monkeypatch):
    # a network that never answers: the window must keep working meanwhile
    release = threading.Event()
    monkeypatch.setattr(viewer, "fetch_latest_release", lambda: release.wait(10) and offline())
    started = time.time()
    app.check_for_updates()
    assert time.time() - started < 0.5  # returned at once, the wait is on the thread
    for _ in range(20):
        app.update()  # the event loop still runs
    assert app._update_check_running
    release.set()
    wait_for_check(app)
    assert not app._update_check_running


class TestAutomaticStart:
    @pytest.fixture
    def started(self, app, monkeypatch):
        calls = []
        monkeypatch.setattr(app, "check_for_updates", lambda: calls.append(True))
        return calls

    def test_not_from_source(self, app, started):
        app._start_auto_update_check()
        assert started == []

    def test_built_app_checks(self, app, started, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        app._start_auto_update_check()
        assert started == [True]

    def test_turned_off(self, app, started, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        app.auto_update_var.set(False)
        app.toggle_auto_update()
        app._start_auto_update_check()
        assert started == []
        assert viewer.load_config()["check_updates"] is False

    def test_checked_today(self, app, started, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        app._config["update_last_check"] = time.time()
        app._start_auto_update_check()
        assert started == []


def test_dialog_opens_over_the_main_window(app):
    # it used to open at the top-left of the main monitor, even with the app on another one
    app.deiconify()
    app.geometry("800x600+300+200")
    app.update()
    app._offer_update(NEWER)
    dialog = app._show_update_dialog()
    dialog.update()
    app_centre = (app.winfo_rootx() + app.winfo_width() // 2, app.winfo_rooty() + app.winfo_height() // 2)
    dialog_centre = (dialog.winfo_rootx() + dialog.winfo_width() // 2,
                     dialog.winfo_rooty() + dialog.winfo_height() // 2)
    assert abs(app_centre[0] - dialog_centre[0]) <= 40
    assert abs(app_centre[1] - dialog_centre[1]) <= 40
