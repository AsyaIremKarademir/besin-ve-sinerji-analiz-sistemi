from __future__ import annotations

import json
import sqlite3

import pytest

from besin_sinerji.data.schema import table_names

CONDITION = json.dumps({"all": [{"component": "nonheme_iron"}, {"component": "vitamin_c"}]})


def _add_source(db, ref_key="nih_iron", url="https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/", doi=None, source_type="fact_sheet", year=None) -> int:
    return db.execute(
        "INSERT INTO Source (ref_key, title, publisher, url, doi, source_type, year) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ref_key, "Iron: Fact Sheet for Health Professionals", "NIH ODS", url, doi, source_type, year),
    ).lastrowid


def _add_rule(db, rule_id="R01", **overrides) -> str:
    data = {
        "rule_id": rule_id,
        "component_a": "nonheme_iron",
        "component_b": "vitamin_c",
        "direction": "supportive",
        "type_label": "Destekleyici",
        "trigger_condition": CONDITION,
        "condition_text": "Öğünde bitkisel demir kaynağı ve C vitamini kaynağı birlikte bulunuyor.",
        "effect_text": "C vitamini non-heme demir emilimini artırabilir.",
        "evidence_level": "well_supported",
        "reviewed_at": "2026-10-04",
    }
    data.update(overrides)
    columns = ", ".join(data)
    placeholders = ", ".join("?" for _ in data)
    db.execute(f"INSERT INTO InteractionRule ({columns}) VALUES ({placeholders})", tuple(data.values()))
    return rule_id


def _link(db, rule_id, source_id):
    db.execute("INSERT INTO RuleSource (rule_id, source_id) VALUES (?, ?)", (rule_id, source_id))


def _activate(db, rule_id):
    db.execute("UPDATE InteractionRule SET status = 'active' WHERE rule_id = ?", (rule_id,))


def _status(db, rule_id):
    return db.execute("SELECT status FROM InteractionRule WHERE rule_id = ?", (rule_id,)).fetchone()[0]


def test_rule_tables_are_created(db):
    assert {"Source", "InteractionRule", "RuleSource"} <= table_names(db)


def test_source_with_url(db):
    _add_source(db)


def test_source_with_doi_only(db):
    _add_source(db, ref_key="mifflin_1990", url=None, doi="10.1093/ajcn/51.2.241", source_type="journal_article", year=1990)


def test_source_needs_url_or_doi(db):
    with pytest.raises(sqlite3.IntegrityError):
        _add_source(db, url=None, doi=None)


@pytest.mark.parametrize(
    ("field", "value"),
    [("url", "ods.od.nih.gov"), ("source_type", "blog"), ("year", 1800)],
)
def test_invalid_source_values(db, field, value):
    with pytest.raises(sqlite3.IntegrityError):
        _add_source(db, **{field: value})


def test_source_ref_key_is_unique(db):
    _add_source(db)
    with pytest.raises(sqlite3.IntegrityError):
        _add_source(db)


def test_new_rule_starts_in_review(db):
    _add_rule(db)

    row = db.execute("SELECT status, version, scope FROM InteractionRule").fetchone()
    assert tuple(row) == ("review", 1, "meal")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rule_id", "kural-1"),
        ("direction", "harmful"),
        ("scope", "everything"),
        ("evidence_level", "kesin"),
        ("status", "draft"),
        ("version", 0),
        ("trigger_condition", "bozuk json"),
        ("trigger_condition", "[]"),
        ("effect_text", "  "),
        ("component_b", "nonheme_iron"),
    ],
)
def test_invalid_rule_values(db, field, value):
    with pytest.raises(sqlite3.IntegrityError):
        _add_rule(db, **{field: value})


def test_rule_cannot_be_inserted_as_active(db):
    with pytest.raises(sqlite3.IntegrityError, match="kaynak"):
        _add_rule(db, status="active")


def test_rule_without_source_cannot_be_activated(db):
    _add_rule(db)

    with pytest.raises(sqlite3.IntegrityError, match="kaynak"):
        _activate(db, "R01")
    assert _status(db, "R01") == "review"


def test_rule_with_source_can_be_activated(db):
    _add_rule(db)
    _link(db, "R01", _add_source(db))

    _activate(db, "R01")

    assert _status(db, "R01") == "active"


def test_active_rule_requires_review_date(db):
    _add_rule(db, reviewed_at=None)
    _link(db, "R01", _add_source(db))

    with pytest.raises(sqlite3.IntegrityError):
        _activate(db, "R01")


def test_rule_can_have_multiple_sources(db):
    _add_rule(db)
    _link(db, "R01", _add_source(db, "nih_iron"))
    _link(db, "R01", _add_source(db, "health_canada_iron", url="https://www.canada.ca/en/health-canada/services/nutrients/iron.html", source_type="guideline"))

    count = db.execute("SELECT COUNT(*) FROM RuleSource WHERE rule_id = 'R01'").fetchone()[0]
    assert count == 2


def test_duplicate_rule_source_link_is_rejected(db):
    _add_rule(db)
    source_id = _add_source(db)
    _link(db, "R01", source_id)
    with pytest.raises(sqlite3.IntegrityError):
        _link(db, "R01", source_id)


def test_last_source_of_active_rule_cannot_be_removed(db):
    _add_rule(db)
    source_id = _add_source(db)
    _link(db, "R01", source_id)
    _activate(db, "R01")

    with pytest.raises(sqlite3.IntegrityError, match="son kaynağı"):
        db.execute("DELETE FROM RuleSource WHERE rule_id = 'R01'")


def test_extra_source_of_active_rule_can_be_removed(db):
    _add_rule(db)
    first = _add_source(db, "nih_iron")
    second = _add_source(db, "health_canada_iron", url="https://www.canada.ca/en/health-canada/services/nutrients/iron.html", source_type="guideline")
    _link(db, "R01", first)
    _link(db, "R01", second)
    _activate(db, "R01")

    db.execute("DELETE FROM RuleSource WHERE rule_id = 'R01' AND source_id = ?", (second,))


def test_retired_rule_can_lose_its_source(db):
    _add_rule(db)
    _link(db, "R01", _add_source(db))
    _activate(db, "R01")
    db.execute("UPDATE InteractionRule SET status = 'retired' WHERE rule_id = 'R01'")

    db.execute("DELETE FROM RuleSource WHERE rule_id = 'R01'")


def test_source_in_use_cannot_be_deleted(db):
    _add_rule(db)
    source_id = _add_source(db)
    _link(db, "R01", source_id)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM Source WHERE source_id = ?", (source_id,))


def test_deleting_active_rule_removes_its_links(db):
    _add_rule(db)
    _link(db, "R01", _add_source(db))
    _activate(db, "R01")

    db.execute("DELETE FROM InteractionRule WHERE rule_id = 'R01'")

    assert db.execute("SELECT COUNT(*) FROM RuleSource").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM Source").fetchone()[0] == 1
