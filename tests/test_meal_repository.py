from __future__ import annotations

import sqlite3

import pytest

from besin_sinerji.data import food_repository as foods
from besin_sinerji.data import meal_repository as repo
from besin_sinerji.data import profile_repository as profiles
from besin_sinerji.data.errors import NotFoundError
from besin_sinerji.data.models import MealItem, UserProfile

USDA = "USDA FoodData Central"


@pytest.fixture
def setup(db):
    user_id = profiles.create_profile(
        db, UserProfile(age=23, sex="female", height_cm=165, weight_kg=58, activity_level="light")
    )
    mercimek = foods.add_food(db, "mercimek", "baklagil", USDA)
    cay = foods.add_food(db, "çay", "icecek", USDA)
    return {"user": user_id, "mercimek": mercimek, "cay": cay}


def _items(setup):
    return [
        MealItem(
            food_id=setup["mercimek"],
            matched_text="1 kase mercimek",
            portion_status="estimated",
            match_confidence=1.0,
            amount_g=200.0,
            portion_note="1 kase ≈ 200 g",
        ),
        MealItem(
            food_id=setup["cay"],
            matched_text="çay",
            portion_status="unknown",
            match_confidence=0.9,
        ),
    ]


def test_create_and_get_meal_with_items(db, setup):
    meal_id = repo.create_meal(db, "  1 kase mercimek ve çay  ", setup["user"], "lunch")
    repo.add_meal_items(db, meal_id, _items(setup))

    meal = repo.get_meal(db, meal_id)

    assert meal.raw_text == "1 kase mercimek ve çay"
    assert meal.meal_time == "lunch"
    assert meal.user_id == setup["user"]
    assert [i.food_name for i in meal.items] == ["mercimek", "çay"]
    assert meal.items[0].amount_g == 200.0
    assert meal.items[0].portion_note == "1 kase ≈ 200 g"
    assert meal.items[1].amount_g is None
    assert meal.items[1].confirmed_by_user is False


def test_meal_needs_clarification_when_portion_unknown(db, setup):
    meal_id = repo.create_meal(db, "mercimek ve çay", setup["user"])
    repo.add_meal_items(db, meal_id, _items(setup))

    assert repo.get_meal(db, meal_id).needs_clarification


def test_meal_without_profile(db, setup):
    meal_id = repo.create_meal(db, "çay")

    meal = repo.get_meal(db, meal_id)

    assert meal.user_id is None
    assert meal.meal_time == "unknown"
    assert meal.items == ()
    assert not meal.needs_clarification


def test_invalid_item_is_rejected(db, setup):
    meal_id = repo.create_meal(db, "bir tabak yemek")
    bad = MealItem(
        food_id=setup["mercimek"],
        matched_text="bir tabak",
        portion_status="unknown",
        match_confidence=0.5,
        amount_g=300.0,
    )

    with pytest.raises(sqlite3.IntegrityError):
        repo.add_meal_item(db, meal_id, bad)


def test_confirm_item_with_amount(db, setup):
    meal_id = repo.create_meal(db, "mercimek ve çay")
    _, cay_item = repo.add_meal_items(db, meal_id, _items(setup))

    repo.confirm_meal_item(db, cay_item, amount_g=200, portion_note="1 su bardağı")

    item = repo.get_meal(db, meal_id).items[1]
    assert item.confirmed_by_user
    assert item.amount_g == 200.0
    assert item.portion_status == "given"
    assert item.portion_note == "1 su bardağı"
    assert not repo.get_meal(db, meal_id).needs_clarification


def test_confirm_item_without_amount_keeps_portion(db, setup):
    meal_id = repo.create_meal(db, "mercimek ve çay")
    mercimek_item, _ = repo.add_meal_items(db, meal_id, _items(setup))

    repo.confirm_meal_item(db, mercimek_item)

    item = repo.get_meal(db, meal_id).items[0]
    assert item.confirmed_by_user
    assert (item.amount_g, item.portion_status) == (200.0, "estimated")


def test_confirm_missing_item_raises(db):
    with pytest.raises(NotFoundError):
        repo.confirm_meal_item(db, 99)


def test_get_missing_meal_raises(db):
    with pytest.raises(NotFoundError, match="Öğün"):
        repo.get_meal(db, 99)


def test_list_meals_newest_first_with_limit(db, setup):
    other_user = profiles.create_profile(
        db, UserProfile(age=40, sex="male", height_cm=180, weight_kg=80, activity_level="active")
    )
    ids = [repo.create_meal(db, f"öğün {i}", setup["user"]) for i in range(3)]
    repo.create_meal(db, "başkasının öğünü", other_user)

    meals = repo.list_meals(db, setup["user"], limit=2)

    assert [m.meal_id for m in meals] == [ids[2], ids[1]]


def test_delete_meal_removes_items_and_results(db, setup):
    meal_id = repo.create_meal(db, "mercimek ve çay")
    repo.add_meal_items(db, meal_id, _items(setup))
    repo.save_analysis(db, meal_id, {"iron_mg": 7.0}, [], "Analiz.")

    repo.delete_meal(db, meal_id)

    for table in ("Meal", "MealItem", "AnalysisResult"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    with pytest.raises(NotFoundError):
        repo.delete_meal(db, meal_id)


def test_save_and_read_analysis_with_turkish_text(db, setup):
    meal_id = repo.create_meal(db, "mercimek ve çay")
    summary = {"demir": {"amount": 6.6, "unit": "mg"}, "not": "çay porsiyonu belirsiz"}
    rules = [{"rule_id": "R02", "label": "Azaltıcı olası etki"}]

    result_id = repo.save_analysis(db, meal_id, summary, rules, "Çay demir emilimini azaltabilir.")

    stored = db.execute(
        "SELECT nutrient_summary FROM AnalysisResult WHERE result_id = ?", (result_id,)
    ).fetchone()[0]
    assert "çay porsiyonu" in stored

    record = repo.get_latest_analysis(db, meal_id)
    assert record.result_id == result_id
    assert record.nutrient_summary == summary
    assert record.triggered_rules == rules
    assert record.response_text == "Çay demir emilimini azaltabilir."


def test_latest_analysis_after_reanalysis(db, setup):
    meal_id = repo.create_meal(db, "mercimek ve çay")
    repo.save_analysis(db, meal_id, {}, [], "Porsiyon belirsiz.")
    second = repo.save_analysis(db, meal_id, {"iron_mg": 6.6}, [], "Netleşmiş analiz.")

    assert repo.get_latest_analysis(db, meal_id).result_id == second
    assert [a.response_text for a in repo.get_analyses(db, meal_id)] == [
        "Porsiyon belirsiz.",
        "Netleşmiş analiz.",
    ]


def test_latest_analysis_is_none_when_not_analyzed(db, setup):
    meal_id = repo.create_meal(db, "çay")

    assert repo.get_latest_analysis(db, meal_id) is None


def test_deleting_profile_removes_meal_history(db, setup):
    meal_id = repo.create_meal(db, "mercimek", setup["user"])
    repo.save_analysis(db, meal_id, {}, [], "Analiz.")

    profiles.delete_profile(db, setup["user"])

    assert repo.list_meals(db, setup["user"]) == []
    with pytest.raises(NotFoundError):
        repo.get_meal(db, meal_id)
