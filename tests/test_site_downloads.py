"""Observable static contracts for the manifest-backed download section."""

from html.parser import HTMLParser
from pathlib import Path


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self._stack = []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "text": "", "parent": self._stack[-1] if self._stack else None}
        self.nodes.append(node)
        self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.nodes.append({"tag": tag, "attrs": dict(attrs), "text": "", "parent": self._stack[-1] if self._stack else None})

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == tag:
                del self._stack[index:]
                return

    def handle_data(self, data):
        for node in self._stack:
            node["text"] += data


def page():
    parser = Page()
    parser.feed(Path("site/index.html").read_text(encoding="utf-8"))
    return parser


def descendants(nodes, ancestor):
    return [node for node in nodes if _is_descendant(node, ancestor)]


def _is_descendant(node, ancestor):
    while node["parent"] is not None:
        if node["parent"] is ancestor:
            return True
        node = node["parent"]
    return False


def platform_card(nodes, platform):
    return next(node for node in nodes if node["attrs"].get("data-release-platform") == platform)


def test_download_section_has_equal_explicit_platform_cards_and_badges():
    document = page()
    section = next(node for node in document.nodes if node["tag"] == "section" and node["attrs"].get("id") == "download")
    cards = descendants(document.nodes, section)
    windows = platform_card(cards, "windows")
    linux = platform_card(cards, "linux")
    assert "Windows" in windows["text"] and "Stable" in windows["text"]
    assert "Linux" in linux["text"] and "Preview" in linux["text"]


def test_each_card_exposes_metadata_action_and_accessible_checksum_copy_feedback():
    document = page()
    for platform in ("windows", "linux"):
        card = platform_card(document.nodes, platform)
        nodes = descendants(document.nodes, card)
        for hook in ("version", "release-date", "package", "architecture", "size", "checksum", "release-notes", "install", "status", "action"):
            assert any(node["attrs"].get("data-release") == hook for node in nodes), (platform, hook)
        copy = next(node for node in nodes if node["attrs"].get("data-release-copy") == "checksum")
        assert copy["tag"] == "button" and copy["attrs"].get("type") == "button"
        assert copy["attrs"].get("aria-label")
        live = next(node for node in nodes if node["attrs"].get("data-release") == "checksum-status")
        assert live["attrs"].get("aria-live") == "polite"


def test_download_routing_is_safe_before_manifest_load_and_has_no_platform_tracking():
    html = Path("site/index.html").read_text(encoding="utf-8")
    document = page()
    for identifier in ("nav-download", "hero-download", "tier-download"):
        link = next(node for node in document.nodes if node["attrs"].get("id") == identifier)
        assert link["attrs"].get("href") == "#download"
    for forbidden in ("navigator.userAgent", "navigator.platform", "beacon", "download event", "addEventListener(\"download", "releases/download/"):
        assert forbidden not in html


def test_download_section_uses_same_origin_module_and_linux_limitations_link():
    document = page()
    scripts = [node for node in document.nodes if node["tag"] == "script"]
    assert any(script["attrs"].get("type") == "module" and script["attrs"].get("src") == "downloads.mjs" for script in scripts)
    linux = platform_card(document.nodes, "linux")
    assert any(node["tag"] == "a" and node["attrs"].get("href") == "linux/" for node in descendants(document.nodes, linux))


def test_no_javascript_visitors_have_a_repository_releases_recovery_link():
    document = page()
    noscript = next(node for node in document.nodes if node["tag"] == "noscript")
    links = descendants(document.nodes, noscript)
    assert any(node["tag"] == "a" and node["attrs"].get("href") == "https://github.com/xhan145/roar/releases" for node in links)


def test_stale_installer_and_checkout_copy_are_not_rendered():
    html = Path("site/index.html").read_text(encoding="utf-8")
    assert "Small installer" not in html
    assert "Card checkout is coming soon" not in html
