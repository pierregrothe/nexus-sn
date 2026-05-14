# tests/test_cli_version_detection.py
# Tests for the /stats.do fallback in _detect_sn_version.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for parsing SN /stats.do as a buildtag fallback."""

from nexus.cli import _parse_stats_do

__all__: list[str] = []


def test_parse_stats_do_plain_text() -> None:
    body = (
        "ServiceNow Build : zurich\n"
        "Build name: Zurich\n"
        "Build tag: glide-zurich-12-15-2024__patch5-04-06-2025\n"
        "Schema Version : 5.43\n"
    )
    build, version = _parse_stats_do(body)
    assert build == "glide-zurich-12-15-2024__patch5-04-06-2025"
    assert version == "Zurich"


def test_parse_stats_do_html_wrapped() -> None:
    body = (
        "<html><body>"
        "<br/>Build tag: glide-yokohama-09-04-2025__patch4-01-22-2026<br/>"
        "<br/>Schema: 5.44<br/>"
        "</body></html>"
    )
    build, version = _parse_stats_do(body)
    assert "yokohama" in build.lower()
    assert version == "Yokohama"


def test_parse_stats_do_missing_buildtag_returns_unknown() -> None:
    body = "Some other status text\nNo buildtag here\nUptime: 12h\n"
    build, version = _parse_stats_do(body)
    assert build == ""
    assert version == "unknown"


def test_parse_stats_do_empty_body() -> None:
    build, version = _parse_stats_do("")
    assert build == ""
    assert version == "unknown"
