"""Veri tabanı bağlantı modülü testleri."""

from __future__ import annotations

import sqlite3

import pytest

from besin_sinerji.data.db import MEMORY_DB, connect, foreign_keys_enabled, get_connection


def _create_parent_child(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE child (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER NOT NULL REFERENCES parent(id)
        );
        """
    )


def test_foreign_keys_are_enabled():
    conn = connect(MEMORY_DB)
    try:
        assert foreign_keys_enabled(conn)
    finally:
        conn.close()


def test_foreign_key_violation_is_rejected():
    conn = connect(MEMORY_DB)
    try:
        _create_parent_child(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO child (parent_id) VALUES (?)", (999,))
    finally:
        conn.close()


def test_rows_are_accessible_by_column_name():
    conn = connect(MEMORY_DB)
    try:
        row = conn.execute("SELECT ? AS name, ? AS amount", ("mercimek", 8.5)).fetchone()
        assert row["name"] == "mercimek"
        assert row["amount"] == 8.5
    finally:
        conn.close()


def test_creates_missing_parent_directory(tmp_path):
    db_file = tmp_path / "alt" / "klasor" / "test.db"

    with get_connection(db_file):
        pass

    assert db_file.exists()


def test_uses_db_path_from_settings(clean_env, monkeypatch, tmp_path):
    db_file = tmp_path / "ayardan.db"
    monkeypatch.setenv("BESIN_DB_PATH", str(db_file))

    with get_connection():
        pass

    assert db_file.exists()


def test_changes_are_committed_on_success(tmp_path):
    db_file = tmp_path / "test.db"

    with get_connection(db_file) as conn:
        _create_parent_child(conn)
        conn.execute("INSERT INTO parent (name) VALUES (?)", ("bulgur",))

    with get_connection(db_file) as conn:
        names = [r["name"] for r in conn.execute("SELECT name FROM parent")]
    assert names == ["bulgur"]


def test_changes_are_rolled_back_on_error(tmp_path):
    db_file = tmp_path / "test.db"
    with get_connection(db_file) as conn:
        _create_parent_child(conn)

    with pytest.raises(RuntimeError):
        with get_connection(db_file) as conn:
            conn.execute("INSERT INTO parent (name) VALUES (?)", ("ayran",))
            raise RuntimeError("işlem ortasında hata")

    with get_connection(db_file) as conn:
        count = conn.execute("SELECT COUNT(*) FROM parent").fetchone()[0]
    assert count == 0


def test_connection_is_closed_after_block(tmp_path):
    with get_connection(tmp_path / "test.db") as conn:
        pass

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_parameterized_query_is_not_injectable():
    conn = connect(MEMORY_DB)
    try:
        _create_parent_child(conn)
        conn.execute("INSERT INTO parent (name) VALUES (?)", ("çay",))
        malicious = "x'; DROP TABLE parent; --"

        rows = conn.execute("SELECT * FROM parent WHERE name = ?", (malicious,)).fetchall()

        assert rows == []
        assert conn.execute("SELECT COUNT(*) FROM parent").fetchone()[0] == 1
    finally:
        conn.close()
