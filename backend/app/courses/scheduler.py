"""Bounded deterministic placement. No DB calls, location generation or LLM."""
from dataclasses import replace
from datetime import timedelta
import math

from app.constraints.defaults import CONFIG, resolve_stay
from app.courses.open_hours import find_slot, opening_windows
from app.domain.course import CourseSettings, Plan, TravelEstimate, Visit


class TravelCache:
    def __init__(self, provider, *, injury: bool):
        self.provider, self.injury = provider, injury
        self.cache = {}
        self.unavailable = False

    def __call__(self, origin, destination):
        key = (origin.id, destination.id)
        if key not in self.cache:
            value = self.provider.estimate(origin, destination, injury=self.injury)
            if value is not None and not isinstance(value, TravelEstimate):
                raise ValueError('travel adapter returned invalid evidence')
            self.cache[key] = value
            self.unavailable |= value is None
        return self.cache[key]


def default_score(place, profile):
    preference = profile.indoorPreference
    if preference.strength == 'SOFT' and preference.value in ('INDOOR', 'OUTDOOR'):
        return int(place.indoor is (preference.value == 'INDOOR'))
    return 0


class CourseScheduler:
    def __init__(self, settings: CourseSettings = CourseSettings(), *, scorer=default_score):
        self.settings, self.scorer = settings, scorer

    def schedule(self, candidates, profile, travel, *, available_window=None) -> Plan:
        # A future anchor orchestrator can pass a narrower free window; anchors
        # themselves, their API and cross-window combination remain #29 work.
        window = available_window or profile.timeWindow.value
        if (window.startAt >= window.endAt or window.startAt < profile.timeWindow.value.startAt
                or window.endAt > profile.timeWindow.value.endAt):
            raise ValueError('scheduling window must stay within the profile')
        injury = 'INJURY' in (profile.mobility.value or ())
        records = sorted((candidate.place for candidate in candidates), key=lambda p: p.id)
        scores = {}
        stays = {}
        for record in records:
            score = self.scorer(record, profile)
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                raise ValueError('invalid soft score')
            scores[record.id] = score
            stays[record.id] = resolve_stay(record.category, facility_minutes=record.default_stay_min).minutes
        best, best_key = Plan(), None
        # Every seed is explored; every valid prefix is an alternative. At most
        # 20 seeds x 6 stops x 20 candidates. Future anchors can split windows.
        for first in records:
            slot = find_slot(first, window.startAt, window.endAt, stays[first.id])
            if slot is None:
                continue
            visits = [Visit(first, *slot, stays[first.id])]
            minutes = []
            while len(visits) < self.settings.max_items:
                used = {visit.place.id for visit in visits}
                choices = []
                for record in records:
                    if record.id in used:
                        continue
                    estimate = travel(visits[-1].place, record)
                    if estimate is None or (injury and estimate.minutes > CONFIG['injury']['maxLegWalkingMinutes']):
                        continue
                    arrival = visits[-1].end_at + timedelta(minutes=estimate.minutes)
                    slot = find_slot(record, arrival, window.endAt, stays[record.id])
                    if slot is not None:
                        choices.append(((-scores[record.id], estimate.minutes, slot[1], record.id), record, slot, estimate.minutes))
                if not choices:
                    break
                _, record, slot, leg_minutes = min(choices, key=lambda choice: choice[0])
                visits.append(Visit(record, *slot, stays[record.id]))
                minutes.append(leg_minutes)
                plan = Plan(tuple(visits), tuple(minutes))
                stay = sum(visit.stay_minutes for visit in visits)
                score = sum(scores[visit.place.id] for visit in visits)
                # #27 may inject a confirmed scorer. No companion weights are
                # invented here. INJURY preference never relaxes a hard rule.
                key = (-len(visits), score, -sum(minutes), stay) if injury else (len(visits), score, stay, -sum(minutes))
                if best_key is None or key > best_key:
                    best, best_key = plan, key
        if injury and best.visits:
            # Give the last visit more available time, bounded by its verified
            # opening interval. No extra travel or invented opening time.
            last = best.visits[-1]
            spans, _ = opening_windows(last.place, last.start_at, window.endAt)
            for opening, closing in spans:
                if opening <= last.start_at and last.end_at <= closing:
                    extra = int((min(closing, window.endAt) - last.end_at).total_seconds() // 60)
                    if extra > 0:
                        last = replace(last, end_at=last.end_at + timedelta(minutes=extra),
                                       stay_minutes=last.stay_minutes + extra)
                        best = Plan((*best.visits[:-1], last), best.travel_minutes)
                    break
        return best
