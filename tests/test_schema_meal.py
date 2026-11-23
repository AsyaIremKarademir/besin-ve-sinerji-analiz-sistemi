"""Öğün ve analiz tablolarının şema testleri (Meal, MealItem, AnalysisResult)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from besin_sinerji.data.schema import table_names


@pytest.fixture
def ids(db):
    """Bir profil, bir gıda ve bir öğün oluşturup kimliklerini döndürür."""
    user_id = db.execute(
        "INSERT INTO UserProfile (age, sex, height_cm, weight_kg, activity_level) "
        "VALUES (?, ?, ?, ?, ?)",
        (23, "female", 165.0, 58.0, "moderate"),
    ).lastrowid
    food_id = db.execute(
        "INSERT INTO Food (name, category, source) VALUES (?, ?, ?)",
        ("mercimek", "baklagil", "USDA FoodData Central"),
    ).lastrowid
    meal_id = _add_meal(db, user_id)
    return {"user": user_id, "food": food_id, "meal": meal_id}


def _add_meal(db, user_id, raw_text="Öğle yemeğinde mercimek ve çay", meal_time="lunch") -> int:
    return db.execute(
        "INSERT INTO Meal (user_id, raw_text, meal_time) VALUES (?, ?, ?)",
        (user_id, raw_text, meal_time),
    ).lastrowid


def _add_item(db, meal_id, food_id, amount_g=200.0, status="given", confidence=0.95) -> int:
    return db.execute(
        "INSERT INTO MealItem (meal_id, food_id, matched_text, amount_g, portion_status, "
        "match_confidence) VALUES (?, ?, ?, ?, ?, ?)",
        (meal_id, food_id, "1 kase mercimek", amount_g, status, confidence),
    ).lastrowid


def _add_result(db, meal_id, summary=None, rules=None, text="Analiz sonucu.") -> int:
    summary = json.dumps({"iron_mg": 6.6}) if summary is None else summary
    rules = "[]" if rules is None else rules
    return db.execute(
        "INSERT INTO AnalysisResult (meal_id, nutrient_summary, triggered_rules, response_text) "
        "VALUES (?, ?, ?, ?)",
        (meal_id, summary, rules, text),
    ).lastrowid


def test_meal_tables_are_created(db):
    assert {"Meal", "MealItem", "AnalysisResult"} <= table_names(db)


# --- Meal -----------------------------------------------------------------------


def test_meal_without_profile_is_allowed(db):
    meal_id = _add_meal(db, None)

    row = db.execute("SELECT user_id, meal_time FROM Meal WHERE meal_id = ?", (meal_id,)).fetchone()
    assert row["user_id"] is None


def test_meal_time_defaults_to_unknown(db):
    meal_id = db.execute("INSERT INTO Meal (raw_text) VALUES (?)", ("çay",)).lastrowid

    assert db.execute("SELECT meal_time FROM Meal WHERE meal_id = ?", (meal_id,)).fetchone()[0] == (
        "unknown"
    )


@pytest.mark.parametrize("text", ["", "   ", "x" * 1001])
def test_meal_text_must_be_non_empty_and_limited(db, text):
    with pytest.raises(sqlite3.IntegrityError):
        _add_meal(db, None, raw_text=text)


def test_invalid_meal_time_is_rejected(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_meal(db, None, meal_time="brunch")


def test_meal_requires_existing_profile(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_meal(db, 999)


# --- MealItem -------------------------------------------------------------------


def test_item_with_given_portion(db, ids):
    item_id = _add_item(db, ids["meal"], ids["food"])

    row = db.execute("SELECT * FROM MealItem WHERE meal_item_id = ?", (item_id,)).fetchone()
    assert row["amount_g"] == 200.0
    assert row["confirmed_by_user"] == 0


def test_unknown_portion_is_stored_without_grams(db, ids):
    _add_item(db, ids["meal"], ids["food"], amount_g=None, status="unknown")


@pytest.mark.parametrize(
    ("amount_g", "status"),
    [
        (None, "given"),  # miktar verildi deniyorsa gram boş olamaz
        (None, "estimated"),
        (150.0, "unknown"),  # miktar bilinmiyorsa gram uydurulamaz
    ],
)
def test_portion_status_and_amount_must_match(db, ids, amount_g, status):
    with pytest.raises(sqlite3.IntegrityError):
        _add_item(db, ids["meal"], ids["food"], amount_g=amount_g, status=status)


@pytest.mark.parametrize("amount_g", [0.0, -50.0])
def test_amount_must_be_positive(db, ids, amount_g):
    with pytest.raises(sqlite3.IntegrityError):
        _add_item(db, ids["meal"], ids["food"], amount_g=amount_g)


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_must_be_between_0_and_1(db, ids, confidence):
    with pytest.raises(sqlite3.IntegrityError):
        _add_item(db, ids["meal"], ids["food"], confidence=confidence)


def test_item_requires_existing_food(db, ids):
    with pytest.raises(sqlite3.IntegrityError):
        _add_item(db, ids["meal"], 999)


def test_food_used_in_history_cannot_be_deleted(db, ids):
    _add_item(db, ids["meal"], ids["food"])

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM Food WHERE food_id = ?", (ids["food"],))


# --- AnalysisResult -------------------------------------------------------------


def test_result_stores_json_snapshot(db, ids):
    rules = json.dumps([{"rule_id": "R01", "type": "supportive"}])
    result_id = _add_result(db, ids["meal"], rules=rules)

    row = db.execute(
        "SELECT nutrient_summary, triggered_rules FROM AnalysisResult WHERE result_id = ?",
        (result_id,),
    ).fetchone()
    assert json.loads(row["nutrient_summary"]) == {"iron_mg": 6.6}
    assert json.loads(row["triggered_rules"])[0]["rule_id"] == "R01"


@pytest.mark.parametrize(
    ("summary", "rules"),
    [
        ("geçersiz json", "[]"),
        ("[1, 2]", "[]"),  # özet bir JSON nesnesi olmalı
        ('{"iron_mg": 1}', "{bozuk"),
        ('{"iron_mg": 1}', '{"rule_id": "R01"}'),  # kurallar bir JSON dizisi olmalı
    ],
)
def test_result_json_fields_are_validated(db, ids, summary, rules):
    with pytest.raises(sqlite3.IntegrityError):
        _add_result(db, ids["meal"], summary=summary, rules=rules)


def test_result_requires_response_text(db, ids):
    with pytest.raises(sqlite3.IntegrityError):
        _add_result(db, ids["meal"], text="  ")


def test_meal_can_have_multiple_results(db, ids):
    # Kullanıcı porsiyonu netleştirdikten sonra öğün yeniden analiz edilebilir.
    _add_result(db, ids["meal"], text="İlk analiz: porsiyon belirsiz.")
    _add_result(db, ids["meal"], text="Porsiyon netleştikten sonraki analiz.")

    count = db.execute(
        "SELECT COUNT(*) FROM AnalysisResult WHERE meal_id = ?", (ids["meal"],)
    ).fetchone()[0]
    assert count == 2


# --- Silme davranışı (gizlilik) ---------------------------------------------------


def test_deleting_profile_deletes_meal_history(db, ids):
    _add_item(db, ids["meal"], ids["food"])
    _add_result(db, ids["meal"])

    db.execute("DELETE FROM UserProfile WHERE user_id = ?", (ids["user"],))

    for table in ("Meal", "MealItem", "AnalysisResult"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    # Gıda kaydı paylaşılan veridir; kullanıcı silinince silinmez.
    assert db.execute("SELECT COUNT(*) FROM Food").fetchone()[0] == 1


def test_food_can_be_deleted_after_history_is_gone(db, ids):
    _add_item(db, ids["meal"], ids["food"])
    db.execute("DELETE FROM Meal WHERE meal_id = ?", (ids["meal"],))

    db.execute("DELETE FROM Food WHERE food_id = ?", (ids["food"],))
