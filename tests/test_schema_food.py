"""Gıda ve besin ögesi tablolarının şema testleri (Food, Nutrient, FoodNutrient, FoodAlias)."""

from __future__ import annotations

import sqlite3

import pytest

from besin_sinerji.data.schema import create_schema, table_names


def _add_food(db, name="mercimek", category="baklagil") -> int:
    cur = db.execute(
        "INSERT INTO Food (name, category, source) VALUES (?, ?, ?)",
        (name, category, "USDA FoodData Central"),
    )
    return cur.lastrowid


def _add_nutrient(db, code="iron", name="Demir", unit="mg", category="mineral") -> int:
    cur = db.execute(
        "INSERT INTO Nutrient (code, name, unit, category) VALUES (?, ?, ?, ?)",
        (code, name, unit, category),
    )
    return cur.lastrowid


def _add_value(db, food_id, nutrient_id, amount, status="measured"):
    db.execute(
        "INSERT INTO FoodNutrient (food_id, nutrient_id, amount_per_100g, status) "
        "VALUES (?, ?, ?, ?)",
        (food_id, nutrient_id, amount, status),
    )


def test_food_tables_are_created(db):
    assert {"Food", "Nutrient", "FoodNutrient", "FoodAlias"} <= table_names(db)


def test_create_schema_is_idempotent(db):
    _add_food(db)

    create_schema(db)

    assert db.execute("SELECT COUNT(*) FROM Food").fetchone()[0] == 1


# --- Food ---------------------------------------------------------------------


def test_food_name_must_be_unique(db):
    _add_food(db, "bulgur", "tahil")
    with pytest.raises(sqlite3.IntegrityError):
        _add_food(db, "bulgur", "tahil")


def test_food_category_must_be_valid(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_food(db, "pizza", "fast_food")


def test_food_source_is_required(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO Food (name, category) VALUES (?, ?)", ("ayran", "sut_urunu"))


# --- Nutrient -----------------------------------------------------------------


def test_nutrient_unit_must_be_valid(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_nutrient(db, unit="kaşık")


def test_nutrient_code_must_be_unique(db):
    _add_nutrient(db)
    with pytest.raises(sqlite3.IntegrityError):
        _add_nutrient(db, name="Demir (tekrar)")


# --- FoodNutrient ---------------------------------------------------------------


def test_measured_value_is_stored(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    _add_value(db, food_id, nutrient_id, 7.5)

    row = db.execute(
        "SELECT amount_per_100g, status FROM FoodNutrient WHERE food_id = ?", (food_id,)
    ).fetchone()
    assert (row["amount_per_100g"], row["status"]) == (7.5, "measured")


def test_zero_is_a_valid_measured_value(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    _add_value(db, food_id, nutrient_id, 0.0)


def test_missing_value_is_null_not_zero(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    _add_value(db, food_id, nutrient_id, None, status="missing")

    amount = db.execute("SELECT amount_per_100g FROM FoodNutrient").fetchone()[0]
    assert amount is None


@pytest.mark.parametrize(
    ("amount", "status"),
    [
        (0.0, "missing"),  # eksik değer 0 olarak girilemez
        (None, "measured"),  # ölçülmüş değer boş bırakılamaz
        (None, "estimated"),
    ],
)
def test_missing_status_and_null_must_match(db, amount, status):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    with pytest.raises(sqlite3.IntegrityError):
        _add_value(db, food_id, nutrient_id, amount, status)


def test_negative_amount_is_rejected(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    with pytest.raises(sqlite3.IntegrityError):
        _add_value(db, food_id, nutrient_id, -1.0)


def test_same_nutrient_twice_for_a_food_is_rejected(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    _add_value(db, food_id, nutrient_id, 7.5)
    with pytest.raises(sqlite3.IntegrityError):
        _add_value(db, food_id, nutrient_id, 8.0)


def test_value_requires_existing_food_and_nutrient(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_value(db, 999, 999, 1.0)


def test_text_amount_is_rejected_by_strict_table(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    with pytest.raises(sqlite3.IntegrityError):
        _add_value(db, food_id, nutrient_id, "çok")


def test_deleting_food_deletes_its_values_and_aliases(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    _add_value(db, food_id, nutrient_id, 7.5)
    db.execute("INSERT INTO FoodAlias (food_id, alias) VALUES (?, ?)", (food_id, "kırmızı mercimek"))

    db.execute("DELETE FROM Food WHERE food_id = ?", (food_id,))

    assert db.execute("SELECT COUNT(*) FROM FoodNutrient").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM FoodAlias").fetchone()[0] == 0


def test_nutrient_in_use_cannot_be_deleted(db):
    food_id, nutrient_id = _add_food(db), _add_nutrient(db)
    _add_value(db, food_id, nutrient_id, 7.5)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM Nutrient WHERE nutrient_id = ?", (nutrient_id,))


# --- FoodAlias ------------------------------------------------------------------


def test_same_alias_can_point_to_different_foods(db):
    beyaz = _add_food(db, "beyaz peynir", "sut_urunu")
    kasar = _add_food(db, "kaşar peyniri", "sut_urunu")

    db.execute("INSERT INTO FoodAlias (food_id, alias) VALUES (?, ?)", (beyaz, "peynir"))
    db.execute("INSERT INTO FoodAlias (food_id, alias) VALUES (?, ?)", (kasar, "peynir"))

    rows = db.execute("SELECT food_id FROM FoodAlias WHERE alias = ?", ("peynir",)).fetchall()
    assert len(rows) == 2


def test_duplicate_alias_for_same_food_is_rejected(db):
    food_id = _add_food(db)
    db.execute("INSERT INTO FoodAlias (food_id, alias) VALUES (?, ?)", (food_id, "mercimek çorbası"))
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO FoodAlias (food_id, alias) VALUES (?, ?)", (food_id, "mercimek çorbası")
        )


def test_blank_alias_is_rejected(db):
    food_id = _add_food(db)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO FoodAlias (food_id, alias) VALUES (?, ?)", (food_id, "   "))
