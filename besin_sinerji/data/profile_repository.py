from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from besin_sinerji.data.errors import NotFoundError
from besin_sinerji.data.models import Allergy, UserProfile

PROFILE_FIELDS = (
    "display_name",
    "age",
    "sex",
    "life_stage",
    "height_cm",
    "weight_kg",
    "activity_level",
    "diet_pattern",
    "goal",
    "health_context",
)


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _profile_values(profile: UserProfile) -> dict[str, object]:
    values = {field: getattr(profile, field) for field in PROFILE_FIELDS}
    values["display_name"] = _blank_to_none(profile.display_name)
    values["health_context"] = _blank_to_none(profile.health_context)
    values["height_cm"] = float(profile.height_cm)
    values["weight_kg"] = float(profile.weight_kg)
    return values


def create_profile(conn: sqlite3.Connection, profile: UserProfile) -> int:
    values = _profile_values(profile)
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    cur = conn.execute(
        f"INSERT INTO UserProfile ({columns}) VALUES ({placeholders})", tuple(values.values())
    )
    user_id = cur.lastrowid
    set_allergies(conn, user_id, profile.allergies)
    return user_id


def get_profile(conn: sqlite3.Connection, user_id: int) -> UserProfile:
    row = conn.execute("SELECT * FROM UserProfile WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFoundError("Profil", user_id)
    return UserProfile(
        **{field: row[field] for field in PROFILE_FIELDS},
        allergies=tuple(get_allergies(conn, user_id)),
        user_id=row["user_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_profiles(conn: sqlite3.Connection) -> list[UserProfile]:
    ids = [r["user_id"] for r in conn.execute("SELECT user_id FROM UserProfile ORDER BY user_id")]
    return [get_profile(conn, user_id) for user_id in ids]


def update_profile(conn: sqlite3.Connection, user_id: int, /, **changes: object) -> UserProfile:
    unknown = set(changes) - set(PROFILE_FIELDS)
    if unknown:
        raise ValueError(f"Güncellenemeyen profil alanları: {', '.join(sorted(unknown))}")
    if not changes:
        return get_profile(conn, user_id)

    for field in ("display_name", "health_context"):
        if field in changes:
            changes[field] = _blank_to_none(changes[field])

    assignments = ", ".join(f"{field} = ?" for field in changes)
    cur = conn.execute(
        f"UPDATE UserProfile SET {assignments} WHERE user_id = ?",
        (*changes.values(), user_id),
    )
    if cur.rowcount == 0:
        raise NotFoundError("Profil", user_id)
    return get_profile(conn, user_id)


def get_allergies(conn: sqlite3.Connection, user_id: int) -> list[Allergy]:
    rows = conn.execute(
        "SELECT allergen, kind, note FROM UserAllergy WHERE user_id = ? ORDER BY allergen",
        (user_id,),
    )
    return [Allergy(r["allergen"], r["kind"], r["note"]) for r in rows]


def set_allergies(
    conn: sqlite3.Connection, user_id: int, allergies: Iterable[Allergy | str]
) -> None:
    items = [Allergy(a) if isinstance(a, str) else a for a in allergies]
    conn.execute("DELETE FROM UserAllergy WHERE user_id = ?", (user_id,))
    conn.executemany(
        "INSERT INTO UserAllergy (user_id, allergen, kind, note) VALUES (?, ?, ?, ?)",
        [(user_id, a.allergen, a.kind, _blank_to_none(a.note)) for a in items],
    )


def delete_profile(conn: sqlite3.Connection, user_id: int) -> None:
    cur = conn.execute("DELETE FROM UserProfile WHERE user_id = ?", (user_id,))
    if cur.rowcount == 0:
        raise NotFoundError("Profil", user_id)
