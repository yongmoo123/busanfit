"""Bounded, category-only context for modification interpretation (DEC-006)."""
from dataclasses import dataclass
from datetime import datetime
from app.domain.place import CONTRACT_CATEGORIES


@dataclass(frozen=True, repr=False)
class ModificationItem:
    order: int
    name: str
    category: str
    indoor: bool | None
    start_at: str
    end_at: str

    def __post_init__(self):
        if type(self.order) is not int or not 1 <= self.order <= 6:
            raise ValueError('invalid order')
        if not isinstance(self.name, str) or not 1 <= len(self.name) <= 200:
            raise ValueError('invalid name')
        if self.category not in CONTRACT_CATEGORIES or (self.indoor is not None and type(self.indoor) is not bool):
            raise ValueError('invalid place summary')
        a, b = datetime.fromisoformat(self.start_at), datetime.fromisoformat(self.end_at)
        if a.tzinfo is None or b.tzinfo is None or a >= b:
            raise ValueError('invalid summary times')
