"""SQLite veri modeli (rapor bölüm 5.4–5.5).

Tablolar ``STRICT`` modunda oluşturulur; SQLite böylece sütun türlerini zorunlu kılar.
Bütün ``CREATE`` ifadeleri ``IF NOT EXISTS`` içerdiği için :func:`create_schema`
birden çok kez güvenle çağrılabilir.

Normalizasyon notları:

* Besin ögesi adı ve birimi yalnızca ``Nutrient`` tablosunda tutulur; ``FoodNutrient``
  yalnızca miktarı saklar. Böylece birim her gıda kaydında tekrar edilmez (3NF).
* Alternatif gıda adları ``Food`` içinde virgüllü liste olarak değil, ayrı ``FoodAlias``
  tablosunda tutulur (1NF: her hücrede tek değer).
* Değeri bilinmeyen besin ögesi ``0`` olarak değil, ``amount_per_100g = NULL`` ve
  ``status = 'missing'`` olarak saklanır. "0" ile "veri yok" birbirinden ayrılır (rapor 4.3).
"""

from __future__ import annotations

import sqlite3

FOOD_CATEGORIES = (
    "baklagil",
    "tahil",
    "sebze",
    "meyve",
    "sut_urunu",
    "et_balik_yumurta",
    "kuruyemis_tohum",
    "yag",
    "icecek",
    "baharat",
    "diger",
)

NUTRIENT_UNITS = ("kcal", "g", "mg", "µg")
NUTRIENT_CATEGORIES = ("enerji", "makro", "vitamin", "mineral", "diger")
VALUE_STATUSES = ("measured", "estimated", "missing")

SEXES = ("female", "male")
LIFE_STAGES = ("none", "pregnant", "lactating")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "active", "very_active")
DIET_PATTERNS = ("omnivore", "vegetarian", "vegan", "pescatarian")
GOALS = ("general", "maintain", "lose", "gain")
ALLERGY_KINDS = ("allergy", "intolerance")
ALLERGENS = (
    "gluten",
    "milk",
    "lactose",
    "egg",
    "peanut",
    "tree_nut",  # fındık, ceviz, badem, antep fıstığı vb.
    "soy",
    "fish",
    "shellfish",
    "sesame",
    "mustard",
    "celery",
    "sulfite",
)

# Profil alanlarının veri tabanı düzeyindeki makul sınırları. Mifflin–St Jeor denklemi
# sağlıklı yetişkinlerde geliştirildiği için sistem yetişkin kullanıcılar için tasarlanmıştır.
AGE_RANGE = (18, 120)
HEIGHT_CM_RANGE = (100.0, 250.0)
WEIGHT_KG_RANGE = (30.0, 300.0)
HEALTH_CONTEXT_MAX_LENGTH = 200


def _sql_list(values: tuple[str, ...]) -> str:
    """Sabit değer listesini CHECK kısıtı için SQL biçimine çevirir."""
    return ", ".join(f"'{v}'" for v in values)


FOOD_TABLES = f"""
CREATE TABLE IF NOT EXISTS Food (
    food_id         INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    category        TEXT    NOT NULL CHECK (category IN ({_sql_list(FOOD_CATEGORIES)})),
    source          TEXT    NOT NULL,           -- örn. 'USDA FoodData Central'
    source_ref      TEXT,                       -- kaynaktaki kimlik, örn. FDC ID
    source_version  TEXT,                       -- kaynak sürümü / erişim tarihi
    note            TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS Nutrient (
    nutrient_id     INTEGER PRIMARY KEY,
    code            TEXT    NOT NULL UNIQUE,    -- koddaki sabit ad, örn. 'iron'
    name            TEXT    NOT NULL,           -- Türkçe görünen ad, örn. 'Demir'
    unit            TEXT    NOT NULL CHECK (unit IN ({_sql_list(NUTRIENT_UNITS)})),
    category        TEXT    NOT NULL CHECK (category IN ({_sql_list(NUTRIENT_CATEGORIES)}))
) STRICT;

CREATE TABLE IF NOT EXISTS FoodNutrient (
    food_id         INTEGER NOT NULL REFERENCES Food(food_id) ON DELETE CASCADE,
    nutrient_id     INTEGER NOT NULL REFERENCES Nutrient(nutrient_id) ON DELETE RESTRICT,
    amount_per_100g REAL    CHECK (amount_per_100g IS NULL OR amount_per_100g >= 0),
    status          TEXT    NOT NULL DEFAULT 'measured'
                            CHECK (status IN ({_sql_list(VALUE_STATUSES)})),
    source_note     TEXT,
    PRIMARY KEY (food_id, nutrient_id),
    -- Eksik değer yalnızca NULL ile, NULL yalnızca eksik değerle gösterilir.
    CHECK ((status = 'missing') = (amount_per_100g IS NULL))
) STRICT;

CREATE TABLE IF NOT EXISTS FoodAlias (
    alias_id        INTEGER PRIMARY KEY,
    food_id         INTEGER NOT NULL REFERENCES Food(food_id) ON DELETE CASCADE,
    alias           TEXT    NOT NULL CHECK (length(trim(alias)) > 0),
    -- Aynı ad farklı gıdalara ait olabilir (örn. 'peynir'); bu belirsizlik
    -- eşleştirme modülünde kullanıcıya sorulur. Aynı gıdada tekrar edemez.
    UNIQUE (food_id, alias)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_food_alias_alias ON FoodAlias(alias);
CREATE INDEX IF NOT EXISTS idx_food_nutrient_nutrient ON FoodNutrient(nutrient_id);
"""

PROFILE_TABLES = f"""
CREATE TABLE IF NOT EXISTS UserProfile (
    user_id         INTEGER PRIMARY KEY,
    display_name    TEXT    CHECK (display_name IS NULL OR length(display_name) <= 50),
    age             INTEGER NOT NULL CHECK (age BETWEEN {AGE_RANGE[0]} AND {AGE_RANGE[1]}),
    sex             TEXT    NOT NULL CHECK (sex IN ({_sql_list(SEXES)})),
    life_stage      TEXT    NOT NULL DEFAULT 'none'
                            CHECK (life_stage IN ({_sql_list(LIFE_STAGES)})),
    height_cm       REAL    NOT NULL
                            CHECK (height_cm BETWEEN {HEIGHT_CM_RANGE[0]} AND {HEIGHT_CM_RANGE[1]}),
    weight_kg       REAL    NOT NULL
                            CHECK (weight_kg BETWEEN {WEIGHT_KG_RANGE[0]} AND {WEIGHT_KG_RANGE[1]}),
    activity_level  TEXT    NOT NULL CHECK (activity_level IN ({_sql_list(ACTIVITY_LEVELS)})),
    diet_pattern    TEXT    NOT NULL DEFAULT 'omnivore'
                            CHECK (diet_pattern IN ({_sql_list(DIET_PATTERNS)})),
    goal            TEXT    NOT NULL DEFAULT 'general' CHECK (goal IN ({_sql_list(GOALS)})),
    -- Kullanıcının isteğe bağlı olarak paylaştığı kısa sağlık bağlamı. Teşhis için
    -- kullanılmaz; yalnızca yanıt dilinde temkin ve profesyonel yönlendirme sağlar (NFR-2).
    health_context  TEXT    CHECK (health_context IS NULL
                                   OR length(health_context) <= {HEALTH_CONTEXT_MAX_LENGTH}),
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Gebelik ve emzirme yalnızca kadın profilinde seçilebilir.
    CHECK (life_stage = 'none' OR sex = 'female')
) STRICT;

CREATE TABLE IF NOT EXISTS UserAllergy (
    user_id         INTEGER NOT NULL REFERENCES UserProfile(user_id) ON DELETE CASCADE,
    allergen        TEXT    NOT NULL CHECK (allergen IN ({_sql_list(ALLERGENS)})),
    kind            TEXT    NOT NULL DEFAULT 'allergy'
                            CHECK (kind IN ({_sql_list(ALLERGY_KINDS)})),
    note            TEXT    CHECK (note IS NULL OR length(note) <= 100),
    PRIMARY KEY (user_id, allergen)
) STRICT;

CREATE TRIGGER IF NOT EXISTS trg_user_profile_updated_at
AFTER UPDATE ON UserProfile
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE UserProfile SET updated_at = CURRENT_TIMESTAMP WHERE user_id = NEW.user_id;
END;
"""

# Sonraki adımlarda eklenecek tablo grupları bu listeye sırayla eklenir.
SCHEMA_PARTS: tuple[str, ...] = (FOOD_TABLES, PROFILE_TABLES)


def create_schema(conn: sqlite3.Connection) -> None:
    """Bütün tabloları ve indeksleri oluşturur (zaten varsa dokunmaz)."""
    for part in SCHEMA_PARTS:
        conn.executescript(part)


def table_names(conn: sqlite3.Connection) -> set[str]:
    """Veri tabanındaki kullanıcı tablolarının adlarını döndürür."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {row["name"] for row in rows}
