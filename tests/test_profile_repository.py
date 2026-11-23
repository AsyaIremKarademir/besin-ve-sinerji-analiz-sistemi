from __future__ import annotations

import sqlite3

import pytest

from besin_sinerji.data import profile_repository as repo
from besin_sinerji.data.errors import NotFoundError
from besin_sinerji.data.models import Allergy, UserProfile


def _profile(**overrides) -> UserProfile:
    data = {
        "age": 23,
        "sex": "female",
        "height_cm": 165,
        "weight_kg": 58,
        "activity_level": "moderate",
        "diet_pattern": "vegetarian",
    }
    data.update(overrides)
    return UserProfile(**data)


def test_create_and_get_profile(db):
    user_id = repo.create_profile(db, _profile(display_name="İrem"))

    profile = repo.get_profile(db, user_id)

    assert profile.user_id == user_id
    assert (profile.age, profile.sex, profile.diet_pattern) == (23, "female", "vegetarian")
    assert profile.height_cm == 165.0
    assert profile.display_name == "İrem"
    assert profile.allergies == ()
    assert profile.created_at and profile.updated_at


def test_blank_optional_texts_are_stored_as_null(db):
    user_id = repo.create_profile(db, _profile(display_name="  ", health_context=""))

    profile = repo.get_profile(db, user_id)

    assert profile.display_name is None
    assert profile.health_context is None


def test_create_profile_with_allergies(db):
    user_id = repo.create_profile(
        db,
        _profile(allergies=(Allergy("tree_nut"), Allergy("lactose", "intolerance"))),
    )

    profile = repo.get_profile(db, user_id)

    assert profile.allergens == {"tree_nut", "lactose"}
    assert Allergy("lactose", "intolerance") in profile.allergies


def test_invalid_profile_is_rejected_without_partial_save(tmp_path):
    from besin_sinerji.data.db import get_connection
    from besin_sinerji.data.schema import create_schema

    db_file = tmp_path / "test.db"
    with get_connection(db_file) as conn:
        create_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        with get_connection(db_file) as conn:
            repo.create_profile(conn, _profile(allergies=(Allergy("çikolata"),)))

    with get_connection(db_file) as conn:
        assert repo.list_profiles(conn) == []


def test_get_missing_profile_raises(db):
    with pytest.raises(NotFoundError, match="Profil"):
        repo.get_profile(db, 7)


def test_list_profiles(db):
    first = repo.create_profile(db, _profile())
    second = repo.create_profile(db, _profile(sex="male", age=30))

    assert [p.user_id for p in repo.list_profiles(db)] == [first, second]


def test_update_profile(db):
    user_id = repo.create_profile(db, _profile())

    updated = repo.update_profile(db, user_id, weight_kg=60.5, goal="maintain")

    assert updated.weight_kg == 60.5
    assert updated.goal == "maintain"
    assert updated.age == 23


def test_update_profile_clears_blank_health_context(db):
    user_id = repo.create_profile(db, _profile(health_context="Demir takviyesi kullanıyorum."))

    assert repo.update_profile(db, user_id, health_context=" ").health_context is None


def test_update_profile_rejects_unknown_fields(db):
    user_id = repo.create_profile(db, _profile())

    with pytest.raises(ValueError, match="user_id"):
        repo.update_profile(db, user_id, user_id=99)
    with pytest.raises(ValueError, match="password"):
        repo.update_profile(db, user_id, password="x")


def test_update_profile_with_invalid_value_is_rejected(db):
    user_id = repo.create_profile(db, _profile())

    with pytest.raises(sqlite3.IntegrityError):
        repo.update_profile(db, user_id, age=12)


def test_update_without_changes_returns_profile(db):
    user_id = repo.create_profile(db, _profile())

    assert repo.update_profile(db, user_id).user_id == user_id


def test_update_missing_profile_raises(db):
    with pytest.raises(NotFoundError):
        repo.update_profile(db, 7, age=30)


def test_set_allergies_replaces_existing(db):
    user_id = repo.create_profile(db, _profile(allergies=(Allergy("egg"),)))

    repo.set_allergies(db, user_id, ["gluten", Allergy("milk", note="  ")])

    allergies = repo.get_allergies(db, user_id)
    assert allergies == [Allergy("gluten"), Allergy("milk")]


def test_set_allergies_can_clear_all(db):
    user_id = repo.create_profile(db, _profile(allergies=(Allergy("egg"),)))

    repo.set_allergies(db, user_id, [])

    assert repo.get_allergies(db, user_id) == []


def test_delete_profile(db):
    user_id = repo.create_profile(db, _profile(allergies=(Allergy("egg"),)))

    repo.delete_profile(db, user_id)

    with pytest.raises(NotFoundError):
        repo.get_profile(db, user_id)
    assert db.execute("SELECT COUNT(*) FROM UserAllergy").fetchone()[0] == 0


def test_delete_missing_profile_raises(db):
    with pytest.raises(NotFoundError):
        repo.delete_profile(db, 7)
