from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from besin_sinerji.data.errors import NotFoundError
from besin_sinerji.data.models import Food, Nutrient, NutrientValue


def clean_name(text: str) -> str:
    lowered = text.replace("I", "ı").replace("İ", "i").lower()
    return " ".join(lowered.split())


def add_nutrient(conn: sqlite3.Connection, code: str, name: str, unit: str, category: str) -> int:
    cur = conn.execute(
        "INSERT INTO Nutrient (code, name, unit, category) VALUES (?, ?, ?, ?)",
        (code.strip(), name.strip(), unit, category),
    )
    return cur.lastrowid


def get_nutrient(conn: sqlite3.Connection, code: str) -> Nutrient:
    row = conn.execute("SELECT * FROM Nutrient WHERE code = ?", (code,)).fetchone()
    if row is None:
        raise NotFoundError("Besin ögesi", code)
    return Nutrient.from_row(row)


def list_nutrients(conn: sqlite3.Connection, category: str | None = None) -> list[Nutrient]:
    if category is None:
        rows = conn.execute("SELECT * FROM Nutrient ORDER BY nutrient_id")
    else:
        rows = conn.execute(
            "SELECT * FROM Nutrient WHERE category = ? ORDER BY nutrient_id", (category,)
        )
    return [Nutrient.from_row(r) for r in rows]


def add_food(
    conn: sqlite3.Connection,
    name: str,
    category: str,
    source: str,
    source_ref: str | None = None,
    source_version: str | None = None,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO Food (name, category, source, source_ref, source_version, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (clean_name(name), category, source, source_ref, source_version, note),
    )
    return cur.lastrowid


def get_food(conn: sqlite3.Connection, food_id: int) -> Food:
    row = conn.execute("SELECT * FROM Food WHERE food_id = ?", (food_id,)).fetchone()
    if row is None:
        raise NotFoundError("Gıda", food_id)
    return Food.from_row(row)


def get_food_by_name(conn: sqlite3.Connection, name: str) -> Food:
    row = conn.execute("SELECT * FROM Food WHERE name = ?", (clean_name(name),)).fetchone()
    if row is None:
        raise NotFoundError("Gıda", name)
    return Food.from_row(row)


def list_foods(conn: sqlite3.Connection, category: str | None = None) -> list[Food]:
    if category is None:
        rows = conn.execute("SELECT * FROM Food ORDER BY name")
    else:
        rows = conn.execute("SELECT * FROM Food WHERE category = ? ORDER BY name", (category,))
    return [Food.from_row(r) for r in rows]


def add_alias(conn: sqlite3.Connection, food_id: int, alias: str) -> int:
    cur = conn.execute(
        "INSERT INTO FoodAlias (food_id, alias) VALUES (?, ?)", (food_id, clean_name(alias))
    )
    return cur.lastrowid


def add_aliases(conn: sqlite3.Connection, food_id: int, aliases: Iterable[str]) -> None:
    for alias in aliases:
        add_alias(conn, food_id, alias)


def get_aliases(conn: sqlite3.Connection, food_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT alias FROM FoodAlias WHERE food_id = ? ORDER BY alias", (food_id,)
    )
    return [r["alias"] for r in rows]


def find_foods(conn: sqlite3.Connection, term: str) -> list[Food]:
    key = clean_name(term)
    rows = conn.execute(
        "SELECT DISTINCT f.* FROM Food f "
        "LEFT JOIN FoodAlias a ON a.food_id = f.food_id "
        "WHERE f.name = ? OR a.alias = ? "
        "ORDER BY f.name",
        (key, key),
    )
    return [Food.from_row(r) for r in rows]


def all_food_terms(conn: sqlite3.Connection) -> dict[str, list[int]]:
    rows = conn.execute(
        "SELECT name AS term, food_id FROM Food "
        "UNION SELECT alias AS term, food_id FROM FoodAlias "
        "ORDER BY term, food_id"
    )
    terms: dict[str, list[int]] = {}
    for row in rows:
        terms.setdefault(row["term"], []).append(row["food_id"])
    return terms


def set_food_nutrient(
    conn: sqlite3.Connection,
    food_id: int,
    nutrient_code: str,
    amount_per_100g: float | None,
    status: str | None = None,
    source_note: str | None = None,
) -> None:
    nutrient = get_nutrient(conn, nutrient_code)
    if status is None:
        status = "missing" if amount_per_100g is None else "measured"
    conn.execute(
        "INSERT INTO FoodNutrient (food_id, nutrient_id, amount_per_100g, status, source_note) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (food_id, nutrient_id) DO UPDATE SET "
        "amount_per_100g = excluded.amount_per_100g, "
        "status = excluded.status, "
        "source_note = excluded.source_note",
        (food_id, nutrient.nutrient_id, amount_per_100g, status, source_note),
    )


def get_food_nutrients(conn: sqlite3.Connection, food_id: int) -> dict[str, NutrientValue]:
    get_food(conn, food_id)
    return get_nutrients_for_foods(conn, [food_id]).get(food_id, {})


def get_nutrients_for_foods(
    conn: sqlite3.Connection, food_ids: Iterable[int]
) -> dict[int, dict[str, NutrientValue]]:
    ids = sorted(set(food_ids))
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT fn.food_id, n.code, n.name, n.unit, fn.amount_per_100g, fn.status, fn.source_note "
        "FROM FoodNutrient fn JOIN Nutrient n ON n.nutrient_id = fn.nutrient_id "
        f"WHERE fn.food_id IN ({placeholders}) "
        "ORDER BY fn.food_id, n.nutrient_id",
        ids,
    )
    result: dict[int, dict[str, NutrientValue]] = {food_id: {} for food_id in ids}
    for row in rows:
        result[row["food_id"]][row["code"]] = NutrientValue(
            code=row["code"],
            name=row["name"],
            unit=row["unit"],
            amount_per_100g=row["amount_per_100g"],
            status=row["status"],
            source_note=row["source_note"],
        )
    return result
