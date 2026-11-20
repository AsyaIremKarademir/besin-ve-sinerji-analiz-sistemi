"""Kullanıcı profili tablolarının şema testleri (UserProfile, UserAllergy)."""

from __future__ import annotations

import sqlite3

import pytest

from besin_sinerji.data.schema import table_names

VALID_PROFILE = {
    "age": 23,
    "sex": "female",
    "height_cm": 165.0,
    "weight_kg": 58.0,
    "activity_level": "moderate",
}


def _add_profile(db, **overrides) -> int:
    data = {**VALID_PROFILE, **overrides}
    columns = ", ".join(data)
    placeholders = ", ".join("?" for _ in data)
    cur = db.execute(
        f"INSERT INTO UserProfile ({columns}) VALUES ({placeholders})", tuple(data.values())
    )
    return cur.lastrowid


def _add_allergy(db, user_id, allergen="tree_nut", kind="allergy"):
    db.execute(
        "INSERT INTO UserAllergy (user_id, allergen, kind) VALUES (?, ?, ?)",
        (user_id, allergen, kind),
    )


def test_profile_tables_are_created(db):
    assert {"UserProfile", "UserAllergy"} <= table_names(db)


def test_valid_profile_gets_defaults(db):
    user_id = _add_profile(db)

    row = db.execute("SELECT * FROM UserProfile WHERE user_id = ?", (user_id,)).fetchone()
    assert row["life_stage"] == "none"
    assert row["diet_pattern"] == "omnivore"
    assert row["goal"] == "general"
    assert row["health_context"] is None
    assert row["created_at"] and row["updated_at"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("age", 17),  # yetişkin olmayan kullanıcı
        ("age", 121),
        ("height_cm", 99.0),
        ("height_cm", 251.0),
        ("weight_kg", 29.0),
        ("weight_kg", 301.0),
        ("sex", "other"),
        ("activity_level", "extreme"),
        ("diet_pattern", "keto"),
        ("goal", "bulk"),
        ("life_stage", "child"),
    ],
)
def test_out_of_range_or_invalid_values_are_rejected(db, field, value):
    with pytest.raises(sqlite3.IntegrityError):
        _add_profile(db, **{field: value})


@pytest.mark.parametrize("field", ["age", "sex", "height_cm", "weight_kg", "activity_level"])
def test_required_fields(db, field):
    data = {k: v for k, v in VALID_PROFILE.items() if k != field}
    columns = ", ".join(data)
    placeholders = ", ".join("?" for _ in data)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            f"INSERT INTO UserProfile ({columns}) VALUES ({placeholders})", tuple(data.values())
        )


def test_age_must_be_integer(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_profile(db, age="yirmi")


@pytest.mark.parametrize("stage", ["pregnant", "lactating"])
def test_life_stage_allowed_for_female(db, stage):
    _add_profile(db, sex="female", life_stage=stage)


@pytest.mark.parametrize("stage", ["pregnant", "lactating"])
def test_life_stage_rejected_for_male(db, stage):
    with pytest.raises(sqlite3.IntegrityError):
        _add_profile(db, sex="male", life_stage=stage)


def test_health_context_length_is_limited(db):
    _add_profile(db, health_context="Doktor kontrolünde demir takviyesi kullanıyorum.")
    with pytest.raises(sqlite3.IntegrityError):
        _add_profile(db, health_context="x" * 201)


def test_updated_at_changes_on_update(db):
    user_id = _add_profile(db)
    db.execute(
        "UPDATE UserProfile SET updated_at = '2000-01-01 00:00:00' WHERE user_id = ?", (user_id,)
    )

    db.execute("UPDATE UserProfile SET weight_kg = 60.0 WHERE user_id = ?", (user_id,))

    row = db.execute(
        "SELECT updated_at, created_at FROM UserProfile WHERE user_id = ?", (user_id,)
    ).fetchone()
    assert row["updated_at"] != "2000-01-01 00:00:00"


# --- UserAllergy ----------------------------------------------------------------


def test_allergies_are_stored_one_per_row(db):
    user_id = _add_profile(db)
    _add_allergy(db, user_id, "tree_nut")
    _add_allergy(db, user_id, "lactose", "intolerance")

    rows = db.execute(
        "SELECT allergen, kind FROM UserAllergy WHERE user_id = ? ORDER BY allergen", (user_id,)
    ).fetchall()
    assert [tuple(r) for r in rows] == [("lactose", "intolerance"), ("tree_nut", "allergy")]


def test_unknown_allergen_is_rejected(db):
    user_id = _add_profile(db)
    with pytest.raises(sqlite3.IntegrityError):
        _add_allergy(db, user_id, "çikolata")


def test_duplicate_allergen_for_user_is_rejected(db):
    user_id = _add_profile(db)
    _add_allergy(db, user_id, "gluten")
    with pytest.raises(sqlite3.IntegrityError):
        _add_allergy(db, user_id, "gluten")


def test_allergy_requires_existing_user(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_allergy(db, 999)


def test_deleting_profile_deletes_allergies(db):
    user_id = _add_profile(db)
    _add_allergy(db, user_id, "egg")

    db.execute("DELETE FROM UserProfile WHERE user_id = ?", (user_id,))

    assert db.execute("SELECT COUNT(*) FROM UserAllergy").fetchone()[0] == 0
