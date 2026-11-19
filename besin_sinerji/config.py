"""Uygulama ayarları.

Ayarlar ortam değişkenlerinden ve (varsa) proje kökündeki ``.env`` dosyasından okunur.
API anahtarı gibi gizli değerler koda veya Git deposuna yazılmaz (NFR-3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv kurulu değilse yalnızca ortam değişkenleri kullanılır
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = PROJECT_ROOT / "data" / "seed"

_DEFAULT_DB_PATH = "data/besin_sinerji.db"
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_TRUE_VALUES = {"1", "true", "evet", "yes", "on"}
_FALSE_VALUES = {"0", "false", "hayir", "hayır", "no", "off", ""}


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} için geçersiz değer: {value!r} (true/false bekleniyor)")


@dataclass(frozen=True)
class Settings:
    """Uygulama genelinde kullanılan, değiştirilemez ayarlar."""

    db_path: Path
    usda_api_key: str | None
    save_history: bool
    log_level: str

    @property
    def has_usda_key(self) -> bool:
        return bool(self.usda_api_key)

    def __repr__(self) -> str:
        # API anahtarının loglara veya hata mesajlarına sızmasını önler.
        key_state = "<ayarlı>" if self.has_usda_key else None
        return (
            f"Settings(db_path={str(self.db_path)!r}, usda_api_key={key_state!r}, "
            f"save_history={self.save_history}, log_level={self.log_level!r})"
        )


def load_settings(env_file: Path | None = None) -> Settings:
    """Ayarları ortam değişkenlerinden okuyup doğrular.

    Args:
        env_file: Okunacak ``.env`` dosyası. Verilmezse proje kökündeki ``.env`` kullanılır.
            Ortamda zaten tanımlı değişkenler ``.env`` tarafından ezilmez.
    """
    if load_dotenv is not None:
        load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)

    db_path = Path(os.getenv("BESIN_DB_PATH", _DEFAULT_DB_PATH))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"LOG_LEVEL için geçersiz değer: {log_level!r} "
            f"(geçerli: {', '.join(sorted(_VALID_LOG_LEVELS))})"
        )

    return Settings(
        db_path=db_path,
        usda_api_key=os.getenv("USDA_API_KEY", "").strip() or None,
        save_history=_parse_bool("SAVE_HISTORY", os.getenv("SAVE_HISTORY", "false")),
        log_level=log_level,
    )
