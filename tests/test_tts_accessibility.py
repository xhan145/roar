from html.parser import HTMLParser
from pathlib import Path


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = {}
        self.labels = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.elements[attrs["id"]] = (tag, attrs)
        if tag == "label" and attrs.get("for"):
            self.labels.add(attrs["for"])


def parse_settings():
    parser = Collector()
    parser.feed(Path("settings.html").read_text(encoding="utf-8"))
    return parser


def test_read_aloud_controls_have_accessible_names_or_labels():
    parsed = parse_settings()
    expected = {
        "tts-enabled", "tts-install", "tts-preload", "tts-remove",
        "tts-voice", "tts-language", "tts-speed", "tts-volume", "tts-output",
        "tts-sample", "tts-preview", "tts-stop-preview", "tts-text",
        "tts-speak", "tts-selected", "tts-clipboard", "tts-stop-all",
        "tts-readback", "tts-stop-dictation", "tts-status-spoken",
        "tts-clipboard-fallback", "tts-hk-selected", "tts-hk-clipboard",
        "tts-hk-pause", "tts-hk-stop", "tts-hk-repeat",
    }
    assert expected <= set(parsed.elements)
    for element_id in expected:
        tag, attrs = parsed.elements[element_id]
        assert (element_id in parsed.labels or attrs.get("aria-label")
                or tag == "button"), element_id


def test_read_aloud_status_is_textual_and_not_color_only():
    parsed = parse_settings()
    _, attrs = parsed.elements["tts-status"]
    assert attrs["role"] == "status"
    assert attrs["aria-live"] == "polite"
    _, message_attrs = parsed.elements["m-tts"]
    assert message_attrs["role"] == "status"


def test_settings_css_supports_focus_high_contrast_and_scaling():
    html = Path("settings.html").read_text(encoding="utf-8")
    assert ":focus-visible" in html
    assert "@media (forced-colors: active)" in html
    assert "prefers-reduced-motion" in html
    # Text areas grow instead of using a clipping fixed height.
    assert "textarea { min-height:" in html


def test_read_aloud_is_a_first_class_keyboard_reachable_section():
    html = Path("settings.html").read_text(encoding="utf-8")
    assert 'class="nav" data-s="readaloud"' in html
    assert '<section id="readaloud">' in html
    assert "314 MiB voice pack plus 1.7 GiB isolated runtime" in html
