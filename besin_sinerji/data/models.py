from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Nutrient:
    nutrient_id: int
    code: str
    name: str
    unit: str
    category: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Nutrient:
        return cls(row["nutrient_id"], row["code"], row["name"], row["unit"], row["category"])


@dataclass(frozen=True)
class Food:
    food_id: int
    name: str
    category: str
    source: str
    source_ref: str | None = None
    source_version: str | None = None
    note: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Food:
        return cls(
            row["food_id"],
            row["name"],
            row["category"],
            row["source"],
            row["source_ref"],
            row["source_version"],
            row["note"],
        )


@dataclass(frozen=True)
class NutrientValue:
    code: str
    name: str
    unit: str
    amount_per_100g: float | None
    status: str
    source_note: str | None = None

    @property
    def is_missing(self) -> bool:
        return self.amount_per_100g is None


@dataclass(frozen=True)
class Allergy:
    allergen: str
    kind: str = "allergy"
    note: str | None = None


@dataclass(frozen=True)
class UserProfile:
    age: int
    sex: str
    height_cm: float
    weight_kg: float
    activity_level: str
    life_stage: str = "none"
    diet_pattern: str = "omnivore"
    goal: str = "general"
    health_context: str | None = None
    display_name: str | None = None
    allergies: tuple[Allergy, ...] = ()
    user_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def allergens(self) -> set[str]:
        return {a.allergen for a in self.allergies}


@dataclass(frozen=True)
class MealItem:
    food_id: int
    matched_text: str
    portion_status: str
    match_confidence: float
    amount_g: float | None = None
    portion_note: str | None = None
    confirmed_by_user: bool = False
    meal_item_id: int | None = None
    food_name: str | None = None


@dataclass(frozen=True)
class Meal:
    meal_id: int
    raw_text: str
    meal_time: str
    created_at: str
    user_id: int | None = None
    items: tuple[MealItem, ...] = ()

    @property
    def needs_clarification(self) -> bool:
        return any(i.portion_status == "unknown" for i in self.items)


@dataclass(frozen=True)
class AnalysisRecord:
    result_id: int
    meal_id: int
    nutrient_summary: dict
    triggered_rules: list
    response_text: str
    created_at: str
