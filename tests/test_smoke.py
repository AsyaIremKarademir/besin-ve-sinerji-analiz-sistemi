"""Duman testleri: paket yapısı ve ayar modülünün temel davranışı."""

from __future__ import annotations

import importlib

import pytest

from besin_sinerji import __version__
from besin_sinerji.config import PROJECT_ROOT, load_settings

MODULES = [
    "besin_sinerji.data",
    "besin_sinerji.profile",
    "besin_sinerji.text",
    "besin_sinerji.nutrition",
    "besin_sinerji.rules",
    "besin_sinerji.response",
]


def test_version_is_defined():
    assert __version__


@pytest.mark.parametrize("module_name", MODULES)
def test_modules_are_importable(module_name):
    assert importlib.import_module(module_name)


def test_default_settings(clean_env):
    settings = load_settings(env_file=clean_env)

    assert settings.db_path == PROJECT_ROOT / "data" / "besin_sinerji.db"
    assert settings.usda_api_key is None
    assert settings.save_history is False
    assert settings.log_level == "INFO"


def test_relative_db_path_is_resolved_from_project_root(clean_env, monkeypatch):
    monkeypatch.setenv("BESIN_DB_PATH", "data/test.db")

    assert load_settings(env_file=clean_env).db_path == PROJECT_ROOT / "data" / "test.db"


def test_api_key_is_hidden_in_repr(clean_env, monkeypatch):
    monkeypatch.setenv("USDA_API_KEY", "gizli-anahtar-123")
    settings = load_settings(env_file=clean_env)

    assert settings.has_usda_key
    assert "gizli-anahtar-123" not in repr(settings)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("Evet", True), ("1", True), ("false", False), ("hayır", False), ("", False)],
)
def test_save_history_parsing(clean_env, monkeypatch, raw, expected):
    monkeypatch.setenv("SAVE_HISTORY", raw)

    assert load_settings(env_file=clean_env).save_history is expected


@pytest.mark.parametrize(("name", "value"), [("SAVE_HISTORY", "belki"), ("LOG_LEVEL", "xyz")])
def test_invalid_values_raise(clean_env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        load_settings(env_file=clean_env)
