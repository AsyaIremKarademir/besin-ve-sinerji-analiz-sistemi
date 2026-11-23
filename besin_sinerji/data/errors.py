from __future__ import annotations


class NotFoundError(LookupError):
    def __init__(self, entity: str, key: object) -> None:
        super().__init__(f"{entity} bulunamadı: {key!r}")
        self.entity = entity
        self.key = key
