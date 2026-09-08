"""Tests for URL detection and link opening."""
import viewer


class TestLooksLikeUrl:
    def test_http_url(self):
        assert viewer.looks_like_url("http://example.com")

    def test_https_url(self):
        assert viewer.looks_like_url("https://example.com/path?x=1")

    def test_www_without_scheme(self):
        assert viewer.looks_like_url("www.example.com")

    def test_strips_surrounding_whitespace(self):
        assert viewer.looks_like_url("  https://example.com  ")

    def test_plain_text_is_not_a_url(self):
        assert not viewer.looks_like_url("just some text")

    def test_empty_string_is_not_a_url(self):
        assert not viewer.looks_like_url("")

    def test_none_is_not_a_url(self):
        assert not viewer.looks_like_url(None)

    def test_url_with_embedded_spaces_rejected(self):
        # a real URL never contains a bare space
        assert not viewer.looks_like_url("https://example.com/some page")


class TestOpenLink:
    def test_adds_scheme_to_www_links(self, monkeypatch):
        opened = {}
        monkeypatch.setattr(viewer.webbrowser, "open", lambda url: opened.setdefault("url", url))

        viewer.open_link("www.example.com")

        assert opened["url"] == "http://www.example.com"

    def test_leaves_full_urls_untouched(self, monkeypatch):
        opened = {}
        monkeypatch.setattr(viewer.webbrowser, "open", lambda url: opened.setdefault("url", url))

        viewer.open_link("https://example.com/path")

        assert opened["url"] == "https://example.com/path"

    def test_strips_whitespace_before_opening(self, monkeypatch):
        opened = {}
        monkeypatch.setattr(viewer.webbrowser, "open", lambda url: opened.setdefault("url", url))

        viewer.open_link("  https://example.com  ")

        assert opened["url"] == "https://example.com"
