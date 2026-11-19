"""FR-018 draft experiment, NEVER registered in the ordinary composition root.

Explicitly load and inject into CourseScheduler(scorer=...) for synthetic review.
Approval and any future ordinary activation require a separate reviewed change.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path
from types import MappingProxyType

from app.courses.scheduler import default_score
from app.domain.place import CONTRACT_CATEGORIES

COMPANION_TYPES = ('COUPLE', 'FAMILY', 'FRIENDS', 'SOLO', 'OTHER')


def finite_weight(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('weight must be a nonnegative finite number')
    try:
        result = float(value)
    except OverflowError:
        raise ValueError('weight must be a nonnegative finite number') from None
    if not math.isfinite(result) or result < 0:
        raise ValueError('weight must be a nonnegative finite number')
    return result


@dataclass(frozen=True, repr=False)
class CompanionProposal:
    version: str
    indoor_weight: float
    companion_weight: float
    category_weights: Mapping[str, Mapping[str, float]]

    def __post_init__(self):
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError('proposal version required')
        if not isinstance(self.category_weights, Mapping) or set(self.category_weights) != set(COMPANION_TYPES):
            raise ValueError('complete companion types required')
        copied = {}
        for kind in COMPANION_TYPES:
            values = self.category_weights[kind]
            if not isinstance(values, Mapping) or set(values) != set(CONTRACT_CATEGORIES):
                raise ValueError('complete contract categories required')
            copied[kind] = MappingProxyType({category: finite_weight(values[category]) for category in CONTRACT_CATEGORIES})
        object.__setattr__(self, 'category_weights', MappingProxyType(copied))
        object.__setattr__(self, 'indoor_weight', finite_weight(self.indoor_weight))
        object.__setattr__(self, 'companion_weight', finite_weight(self.companion_weight))


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate proposal key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('non-finite JSON number')


def load_companion_proposal(path=None) -> CompanionProposal:
    path = Path(path) if path is not None else Path(__file__).resolve().parents[3] / 'config/companion-weights.proposal.json'
    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    required = {'version', 'status', 'pmApproved', 'indoorPreferenceWeight', 'companionCategoryWeight', 'categoryWeights'}
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError('invalid proposal keys')
    if data['status'] != 'PROPOSAL' or data['pmApproved'] is not False:
        raise ValueError('this loader is only for unapproved proposal experiments')
    return CompanionProposal(data['version'], data['indoorPreferenceWeight'],
                             data['companionCategoryWeight'], data['categoryWeights'])


@dataclass(frozen=True)
class ScoreBreakdown:
    indoor: float
    companion_category: float

    @property
    def total(self):
        result = self.indoor + self.companion_category
        if not math.isfinite(result):
            raise ValueError('non-finite combined score')
        return result


class ProposalCompanionScorer:
    def __init__(self, proposal: CompanionProposal):
        if not isinstance(proposal, CompanionProposal):
            raise ValueError('validated proposal required')
        self.proposal = proposal

    def breakdown(self, place, profile) -> ScoreBreakdown:
        if place.category not in CONTRACT_CATEGORIES:
            raise ValueError('unknown place category')
        condition = profile.companions
        weight = 0
        # HARD companions remain unsupported by CourseService, not softened here.
        if condition.value is not None and condition.source != 'UNSET' and condition.strength == 'SOFT':
            weight = self.proposal.category_weights[condition.value.type][place.category]
        # No name/overview parsing, price, count, hasInfant or suitability inference.
        parts = ScoreBreakdown(self.proposal.indoor_weight * default_score(place, profile),
                               self.proposal.companion_weight * weight)
        _ = parts.total  # Fail clearly on arithmetic overflow, never hide it as zero.
        return parts

    def __call__(self, place, profile):
        return self.breakdown(place, profile).total
