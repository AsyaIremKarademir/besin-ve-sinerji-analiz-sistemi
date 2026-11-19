"""Tüm testlerde ortak kullanılan pytest fixture'ları."""

from __future__ import annotations

import pytest

# Testlerin geliştiricinin kendi ortamından veya .env dosyasından etkilenmemesi için
# her testten önce temizlenen ortam değişkenleri.
_APP_ENV_VARS = ("BESIN_DB_PATH", "USDA_API_KEY", "SAVE_HISTORY", "LOG_LEVEL")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Uygulama ortam değişkenlerini temizler ve var olmayan bir .env yolu döndürür.

    Dönen yol ``load_settings(env_file=...)`` parametresine verilerek
    proje kökündeki gerçek ``.env`` dosyasının okunması engellenir.
    """
    for name in _APP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "olmayan.env"


@pytest.fixture
def db():
    """Şeması kurulmuş, bellekte çalışan boş bir veri tabanı bağlantısı."""
    from besin_sinerji.data.db import MEMORY_DB, connect
    from besin_sinerji.data.schema import create_schema

    conn = connect(MEMORY_DB)
    create_schema(conn)
    yield conn
    conn.close()
