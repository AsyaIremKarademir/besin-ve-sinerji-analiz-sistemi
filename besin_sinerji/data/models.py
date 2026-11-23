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
