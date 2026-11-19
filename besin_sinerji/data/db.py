"""SQLite bağlantı yönetimi.

Bütün veri tabanı erişimi bu modüldeki fonksiyonlar üzerinden yapılır. Böylece:

* her bağlantıda yabancı anahtar denetimi açılır (SQLite'ta varsayılan olarak kapalıdır),
* satırlar sütun adıyla okunabilir (``row["name"]``),
* işlemler (transaction) başarıyla biterse kaydedilir, hata olursa geri alınır.

Sorgular her zaman parametreli yazılmalıdır (NFR-3)::

    conn.execute("SELECT * FROM Food WHERE name = ?", (name,))   # doğru
    conn.execute(f"SELECT * FROM Food WHERE name = '{name}'")     # YANLIŞ: SQL enjeksiyonu
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from besin_sinerji.config import load_settings

MEMORY_DB = ":memory:"

# Kilitli veri tabanında hata vermeden önce beklenecek süre (saniye).
_BUSY_TIMEOUT_SECONDS = 5.0


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Ayarları uygulanmış yeni bir SQLite bağlantısı açar.

    Args:
        db_path: Veri tabanı dosyası. Verilmezse ayarlardaki ``BESIN_DB_PATH`` kullanılır.
            Testler için ``":memory:"`` verilebilir.

    Bağlantıyı kapatmak çağıranın sorumluluğundadır; mümkünse :func:`get_connection`
    kullanılmalıdır.
    """
    if db_path is None:
        db_path = load_settings().db_path

    if str(db_path) != MEMORY_DB:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=_BUSY_TIMEOUT_SECONDS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Bağlantıyı tek bir işlem (transaction) olarak yönetir.

    Blok hatasız biterse değişiklikler kaydedilir; hata olursa geri alınır.
    Her iki durumda da bağlantı kapatılır.

    Örnek::

        with get_connection() as conn:
            conn.execute("INSERT INTO Food (name) VALUES (?)", ("mercimek",))
    """
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def foreign_keys_enabled(conn: sqlite3.Connection) -> bool:
    """Bağlantıda yabancı anahtar denetiminin açık olup olmadığını döndürür."""
    return bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
