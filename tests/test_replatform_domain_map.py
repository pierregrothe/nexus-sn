# tests/test_replatform_domain_map.py
# Tests for the scope->domain YAML overlay loader.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Behavioral tests for nexus.replatform.domain_map.load_domain_map."""

from pathlib import Path

import pytest

from nexus.replatform.domain_map import load_domain_map

__all__: list[str] = []


def test_load_domain_map_parses_flat_mapping(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text("x_cibc_hr: HR\nx_cibc_kyc: Lending Ops\n", encoding="utf-8")
    assert load_domain_map(path) == {"x_cibc_hr": "HR", "x_cibc_kyc": "Lending Ops"}


def test_load_domain_map_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping of scope -> domain"):
        load_domain_map(path)


def test_load_domain_map_rejects_non_string_values(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text("x_cibc_hr: 42\n", encoding="utf-8")
    with pytest.raises(ValueError, match="string scopes to string domains"):
        load_domain_map(path)


def test_load_domain_map_rejects_invalid_yaml_syntax(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text("foo: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid YAML"):
        load_domain_map(path)
