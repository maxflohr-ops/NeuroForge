"""Tests for the ytgrab argument builder — the part that has to be right."""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "ytgrab", Path(__file__).with_name("ytgrab.py")
)
ytgrab = importlib.util.module_from_spec(spec)
sys.modules["ytgrab"] = ytgrab
spec.loader.exec_module(ytgrab)


def cfg(**over):
    return {**ytgrab.DEFAULT_CONFIG, **over}


def args(config, urls=("https://youtu.be/x",), ffmpeg=True, monkeypatch=None):
    monkeypatch.setattr(ytgrab, "have_ffmpeg", lambda: ffmpeg)
    return ytgrab.build_args(config, list(urls))


def test_sponsors_are_cut_by_default(monkeypatch):
    out = args(cfg(), monkeypatch=monkeypatch)
    removed = out[out.index("--sponsorblock-remove") + 1].split(",")
    assert removed == ytgrab.SB_NORMAL


def test_aggressive_mode_cuts_intros_and_selfpromo(monkeypatch):
    out = args(cfg(sponsorblock="aggressive"), monkeypatch=monkeypatch)
    removed = out[out.index("--sponsorblock-remove") + 1].split(",")
    assert {"intro", "outro", "music_offtopic"} <= set(removed)


def test_sponsorblock_off(monkeypatch):
    assert "--sponsorblock-remove" not in args(cfg(sponsorblock="off"),
                                               monkeypatch=monkeypatch)


def test_sponsorblock_needs_ffmpeg(monkeypatch):
    """Cutting segments is an ffmpeg job; skip it rather than fail the download."""
    assert "--sponsorblock-remove" not in args(cfg(), ffmpeg=False,
                                               monkeypatch=monkeypatch)


def test_audio_mode_extracts_and_skips_container_merge(monkeypatch):
    out = args(cfg(quality="audio", audio_format="mp3"), monkeypatch=monkeypatch)
    assert "--extract-audio" in out
    assert out[out.index("--audio-format") + 1] == "mp3"
    assert "--merge-output-format" not in out


def test_quality_cap_falls_back_instead_of_failing():
    sel = ytgrab.format_selector(cfg(quality="1080p"))
    assert "height<=1080" in sel
    assert sel.endswith("bestvideo*+bestaudio/best")


def test_every_quality_produces_a_selector():
    for q in ytgrab.QUALITIES:
        assert ytgrab.format_selector(cfg(quality=q))


def test_playlist_off_by_default(monkeypatch):
    assert "--no-playlist" in args(cfg(), monkeypatch=monkeypatch)
    assert "--yes-playlist" in args(cfg(playlist=True), monkeypatch=monkeypatch)


def test_playlist_template_is_a_usable_path():
    tmpl = ytgrab.output_template(cfg(playlist=True, output_dir="/tmp/v"))
    assert tmpl.startswith("/tmp/v/")
    assert tmpl.endswith(".%(ext)s")


def test_urls_come_last_behind_a_separator(monkeypatch):
    out = args(cfg(), urls=("https://youtu.be/a", "https://youtu.be/b"),
               monkeypatch=monkeypatch)
    assert out[-3:] == ["--", "https://youtu.be/a", "https://youtu.be/b"]


def test_bot_check_failure_suggests_cookies():
    hint = ytgrab._hint_for("ERROR: Sign in to confirm you're not a bot")
    assert hint and "cookies" in hint.lower()


def test_extraction_failure_suggests_update():
    assert "update" in ytgrab._hint_for("ERROR: unable to extract player response")


# --- pasting ---------------------------------------------------------------

def test_a_plain_pasted_link_is_a_url():
    assert ytgrab.normalize_url("https://www.youtube.com/watch?v=abc") == \
        "https://www.youtube.com/watch?v=abc"


def test_share_sheet_link_without_a_scheme_gets_one():
    assert ytgrab.normalize_url("youtu.be/abc?si=xyz") == "https://youtu.be/abc?si=xyz"
    assert ytgrab.normalize_url("www.youtube.com/watch?v=abc").startswith("https://")
    assert ytgrab.normalize_url("m.youtube.com/watch?v=abc").startswith("https://")


def test_quotes_brackets_and_trailing_punctuation_are_stripped():
    for pasted in ('"https://youtu.be/abc"', "<https://youtu.be/abc>",
                   "https://youtu.be/abc,", "'https://youtu.be/abc'"):
        assert ytgrab.normalize_url(pasted) == "https://youtu.be/abc"


def test_query_strings_survive_stripping():
    url = "https://www.youtube.com/watch?v=abc&t=90s&list=PL123"
    assert ytgrab.normalize_url(url) == url


def test_several_links_in_one_paste():
    assert ytgrab.extract_urls("https://youtu.be/a https://youtu.be/b") == \
        ["https://youtu.be/a", "https://youtu.be/b"]
    assert ytgrab.extract_urls("youtu.be/a, youtu.be/b") == \
        ["https://youtu.be/a", "https://youtu.be/b"]


def test_commands_are_not_mistaken_for_links():
    for line in ("help", "set quality 1080p", "audio https://youtu.be/a", "quit"):
        assert ytgrab.extract_urls(line) == []


def test_search_terms_pass_through():
    assert ytgrab.normalize_url("ytsearch5:lofi beats") == "ytsearch5:lofi beats"
