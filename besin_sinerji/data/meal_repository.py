from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from besin_sinerji.data.errors import NotFoundError
from besin_sinerji.data.models import AnalysisRecord, Meal, MealItem


def create_meal(
    conn: sqlite3.Connection,
    raw_text: str,
    user_id: int | None = None,
    meal_time: str = "unknown",
) -> int:
    cur = conn.execute(
        "INSERT INTO Meal (user_id, raw_text, meal_time) VALUES (?, ?, ?)",
        (user_id, raw_text.strip(), meal_time),
    )
    return cur.lastrowid


def add_meal_item(conn: sqlite3.Connection, meal_id: int, item: MealItem) -> int:
    cur = conn.execute(
        "INSERT INTO MealItem (meal_id, food_id, matched_text, amount_g, portion_status, "
        "portion_note, match_confidence, confirmed_by_user) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            meal_id,
            item.food_id,
            item.matched_text,
            item.amount_g,
            item.portion_status,
            item.portion_note,
            float(item.match_confidence),
            int(item.confirmed_by_user),
        ),
    )
    return cur.lastrowid


def add_meal_items(conn: sqlite3.Connection, meal_id: int, items: Iterable[MealItem]) -> list[int]:
    return [add_meal_item(conn, meal_id, item) for item in items]


def confirm_meal_item(
    conn: sqlite3.Connection,
    meal_item_id: int,
    amount_g: float | None = None,
    portion_note: str | None = None,
) -> None:
    if amount_g is None:
        cur = conn.execute(
            "UPDATE MealItem SET confirmed_by_user = 1 WHERE meal_item_id = ?", (meal_item_id,)
        )
    else:
        cur = conn.execute(
            "UPDATE MealItem SET confirmed_by_user = 1, amount_g = ?, portion_status = 'given', "
            "portion_note = ? WHERE meal_item_id = ?",
            (float(amount_g), portion_note, meal_item_id),
        )
    if cur.rowcount == 0:
        raise NotFoundError("Öğün kalemi", meal_item_id)


def _item_from_row(row: sqlite3.Row) -> MealItem:
    return MealItem(
        food_id=row["food_id"],
        matched_text=row["matched_text"],
        portion_status=row["portion_status"],
        match_confidence=row["match_confidence"],
        amount_g=row["amount_g"],
        portion_note=row["portion_note"],
        confirmed_by_user=bool(row["confirmed_by_user"]),
        meal_item_id=row["meal_item_id"],
        food_name=row["food_name"],
    )


def get_meal_items(conn: sqlite3.Connection, meal_id: int) -> list[MealItem]:
    rows = conn.execute(
        "SELECT mi.*, f.name AS food_name FROM MealItem mi "
        "JOIN Food f ON f.food_id = mi.food_id "
        "WHERE mi.meal_id = ? ORDER BY mi.meal_item_id",
        (meal_id,),
    )
    return [_item_from_row(r) for r in rows]


def get_meal(conn: sqlite3.Connection, meal_id: int) -> Meal:
    row = conn.execute("SELECT * FROM Meal WHERE meal_id = ?", (meal_id,)).fetchone()
    if row is None:
        raise NotFoundError("Öğün", meal_id)
    return Meal(
        meal_id=row["meal_id"],
        raw_text=row["raw_text"],
        meal_time=row["meal_time"],
        created_at=row["created_at"],
        user_id=row["user_id"],
        items=tuple(get_meal_items(conn, meal_id)),
    )


def list_meals(conn: sqlite3.Connection, user_id: int, limit: int = 20) -> list[Meal]:
    rows = conn.execute(
        "SELECT meal_id FROM Meal WHERE user_id = ? "
        "ORDER BY created_at DESC, meal_id DESC LIMIT ?",
        (user_id, limit),
    )
    return [get_meal(conn, r["meal_id"]) for r in rows]


def delete_meal(conn: sqlite3.Connection, meal_id: int) -> None:
    cur = conn.execute("DELETE FROM Meal WHERE meal_id = ?", (meal_id,))
    if cur.rowcount == 0:
        raise NotFoundError("Öğün", meal_id)


def save_analysis(
    conn: sqlite3.Connection,
    meal_id: int,
    nutrient_summary: dict,
    triggered_rules: list,
    response_text: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO AnalysisResult (meal_id, nutrient_summary, triggered_rules, response_text) "
        "VALUES (?, ?, ?, ?)",
        (
            meal_id,
            json.dumps(nutrient_summary, ensure_ascii=False),
            json.dumps(triggered_rules, ensure_ascii=False),
            response_text,
        ),
    )
    return cur.lastrowid


def _analysis_from_row(row: sqlite3.Row) -> AnalysisRecord:
    return AnalysisRecord(
        result_id=row["result_id"],
        meal_id=row["meal_id"],
        nutrient_summary=json.loads(row["nutrient_summary"]),
        triggered_rules=json.loads(row["triggered_rules"]),
        response_text=row["response_text"],
        created_at=row["created_at"],
    )


def get_analyses(conn: sqlite3.Connection, meal_id: int) -> list[AnalysisRecord]:
    rows = conn.execute(
        "SELECT * FROM AnalysisResult WHERE meal_id = ? ORDER BY result_id", (meal_id,)
    )
    return [_analysis_from_row(r) for r in rows]


def get_latest_analysis(conn: sqlite3.Connection, meal_id: int) -> AnalysisRecord | None:
    row = conn.execute(
        "SELECT * FROM AnalysisResult WHERE meal_id = ? ORDER BY result_id DESC LIMIT 1",
        (meal_id,),
    ).fetchone()
    return None if row is None else _analysis_from_row(row)
