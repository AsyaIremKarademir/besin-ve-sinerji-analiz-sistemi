from __future__ import annotations

import sqlite3

import pytest

from besin_sinerji.data import food_repository as repo
from besin_sinerji.data.errors import NotFoundError

USDA = "USDA FoodData Central"


@pytest.fixture
def nutrients(db):
    repo.add_nutrient(db, "energy", "Enerji", "kcal", "enerji")
    repo.add_nutrient(db, "protein", "Protein", "g", "makro")
    repo.add_nutrient(db, "iron", "Demir", "mg", "mineral")
    repo.add_nutrient(db, "vitamin_c", "C vitamini", "mg", "vitamin")
    return db


@pytest.fixture
def mercimek(nutrients):
    food_id = repo.add_food(nutrients, "Mercimek", "baklagil", USDA, source_ref="172420")
    repo.add_aliases(nutrients, food_id, ["kırmızı mercimek", "mercimek çorbası"])
    return food_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Kırmızı   Mercimek ", "kırmızı mercimek"),
        ("ISPANAK", "ıspanak"),
        ("İNCİR", "incir"),
        ("Çay", "çay"),
    ],
)
def test_clean_name_handles_turkish_letters_and_spaces(raw, expected):
    assert repo.clean_name(raw) == expected


def test_get_nutrient(nutrients):
    iron = repo.get_nutrient(nutrients, "iron")

    assert (iron.name, iron.unit, iron.category) == ("Demir", "mg", "mineral")


def test_unknown_nutrient_raises(nutrients):
    with pytest.raises(NotFoundError, match="Besin ögesi"):
        repo.get_nutrient(nutrients, "unobtainium")


def test_list_nutrients_by_category(nutrients):
    assert [n.code for n in repo.list_nutrients(nutrients)] == [
        "energy",
        "protein",
        "iron",
        "vitamin_c",
    ]
    assert [n.code for n in repo.list_nutrients(nutrients, "mineral")] == ["iron"]


def test_food_name_is_stored_clean(mercimek, db):
    food = repo.get_food(db, mercimek)

    assert food.name == "mercimek"
    assert food.source == USDA
    assert food.source_ref == "172420"


def test_get_food_by_name_ignores_case(mercimek, db):
    assert repo.get_food_by_name(db, "MERCİMEK").food_id == mercimek


def test_missing_food_raises(db):
    with pytest.raises(NotFoundError, match="Gıda"):
        repo.get_food(db, 42)
    with pytest.raises(NotFoundError):
        repo.get_food_by_name(db, "pizza")


def test_list_foods_by_category(mercimek, db):
    repo.add_food(db, "bulgur", "tahil", USDA)
    repo.add_food(db, "ayran", "sut_urunu", USDA)

    assert [f.name for f in repo.list_foods(db)] == ["ayran", "bulgur", "mercimek"]
    assert [f.name for f in repo.list_foods(db, "tahil")] == ["bulgur"]


def test_aliases_are_cleaned_and_listed(mercimek, db):
    repo.add_alias(db, mercimek, "  Yeşil MERCİMEK ")

    assert repo.get_aliases(db, mercimek) == [
        "kırmızı mercimek",
        "mercimek çorbası",
        "yeşil mercimek",
    ]


def test_find_foods_by_name_or_alias(mercimek, db):
    assert [f.food_id for f in repo.find_foods(db, "mercimek")] == [mercimek]
    assert [f.food_id for f in repo.find_foods(db, "Kırmızı Mercimek")] == [mercimek]
    assert repo.find_foods(db, "nohut") == []


def test_find_foods_returns_all_candidates_for_ambiguous_alias(db):
    beyaz = repo.add_food(db, "beyaz peynir", "sut_urunu", USDA)
    kasar = repo.add_food(db, "kaşar peyniri", "sut_urunu", USDA)
    repo.add_alias(db, beyaz, "peynir")
    repo.add_alias(db, kasar, "peynir")

    names = [f.name for f in repo.find_foods(db, "peynir")]

    assert names == ["beyaz peynir", "kaşar peyniri"]


def test_find_foods_does_not_duplicate_when_name_and_alias_match(db):
    food_id = repo.add_food(db, "çay", "icecek", USDA)
    repo.add_alias(db, food_id, "çay")

    assert len(repo.find_foods(db, "çay")) == 1


def test_all_food_terms(mercimek, db):
    terms = repo.all_food_terms(db)

    assert terms == {
        "mercimek": [mercimek],
        "kırmızı mercimek": [mercimek],
        "mercimek çorbası": [mercimek],
    }


def test_set_and_get_food_nutrients(mercimek, db):
    repo.set_food_nutrient(db, mercimek, "energy", 352.0)
    repo.set_food_nutrient(db, mercimek, "iron", 6.51, source_note="FDC 172420")

    values = repo.get_food_nutrients(db, mercimek)

    assert set(values) == {"energy", "iron"}
    assert values["iron"].amount_per_100g == 6.51
    assert values["iron"].unit == "mg"
    assert values["iron"].status == "measured"
    assert values["iron"].source_note == "FDC 172420"


def test_missing_value_gets_missing_status(mercimek, db):
    repo.set_food_nutrient(db, mercimek, "vitamin_c", None)

    value = repo.get_food_nutrients(db, mercimek)["vitamin_c"]

    assert value.is_missing
    assert value.status == "missing"


def test_set_food_nutrient_updates_existing_value(mercimek, db):
    repo.set_food_nutrient(db, mercimek, "iron", 6.0)
    repo.set_food_nutrient(db, mercimek, "iron", 6.51, status="estimated")

    value = repo.get_food_nutrients(db, mercimek)["iron"]

    assert (value.amount_per_100g, value.status) == (6.51, "estimated")


def test_set_food_nutrient_rejects_unknown_nutrient(mercimek, db):
    with pytest.raises(NotFoundError):
        repo.set_food_nutrient(db, mercimek, "unobtainium", 1.0)


def test_set_food_nutrient_rejects_zero_marked_as_missing(mercimek, db):
    with pytest.raises(sqlite3.IntegrityError):
        repo.set_food_nutrient(db, mercimek, "iron", 0.0, status="missing")


def test_get_food_nutrients_for_unknown_food_raises(db):
    with pytest.raises(NotFoundError):
        repo.get_food_nutrients(db, 42)


def test_get_nutrients_for_foods_in_one_query(mercimek, db):
    portakal = repo.add_food(db, "portakal", "meyve", USDA)
    bos = repo.add_food(db, "su", "icecek", USDA)
    repo.set_food_nutrient(db, mercimek, "iron", 6.51)
    repo.set_food_nutrient(db, portakal, "vitamin_c", 53.2)

    result = repo.get_nutrients_for_foods(db, [portakal, mercimek, portakal, bos])

    assert set(result) == {mercimek, portakal, bos}
    assert result[mercimek]["iron"].amount_per_100g == 6.51
    assert result[portakal]["vitamin_c"].amount_per_100g == 53.2
    assert result[bos] == {}


def test_get_nutrients_for_no_foods(db):
    assert repo.get_nutrients_for_foods(db, []) == {}
