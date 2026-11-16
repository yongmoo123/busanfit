"""Bounded explanation facts, independent of DB/HTTP/provider implementations."""
from dataclasses import dataclass
from typing import Literal
from app.domain.place import CONTRACT_CATEGORIES

FactKey = Literal['CATEGORY', 'STAY', 'INDOOR', 'OUTDOOR', 'WHEELCHAIR', 'STROLLER']
FACT_KEYS = ('CATEGORY', 'STAY', 'INDOOR', 'OUTDOOR', 'WHEELCHAIR', 'STROLLER')


@dataclass(frozen=True, repr=False)
class ExplanationPlace:
    place_id: str
    name: str
    category: str
    overview: str | None
    allowed_facts: tuple[FactKey, ...]

    def __post_init__(self):
        if not isinstance(self.place_id, str) or not self.place_id or not isinstance(self.name, str):
            raise ValueError('invalid explanation place identity')
        if self.category not in CONTRACT_CATEGORIES:
            raise ValueError('invalid explanation category')
        if self.overview is not None and (not isinstance(self.overview, str) or len(self.overview) > 200):
            raise ValueError('overview must be bounded')
        if (not isinstance(self.allowed_facts, tuple) or not self.allowed_facts
                or not all(key in FACT_KEYS for key in self.allowed_facts)
                or len(set(self.allowed_facts)) != len(self.allowed_facts)):
            raise ValueError('invalid allowed facts')
