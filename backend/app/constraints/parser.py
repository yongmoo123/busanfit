"""Conservative keyword skeleton. No session merge or HTTP decisions."""
from datetime import datetime, timedelta, timezone
import re
from app.domain.extraction import CompanionHints, ExtractedCondition, Extraction, TimeRange


SEOUL = timezone(timedelta(hours=9))
FIELDS = ('area', 'time_window', 'transport', 'mobility', 'budget',
          'indoor_preference', 'companions', 'excluded_categories', 'preference_tags')
# A clause containing these markers is deliberately not resolved by keywords.
AMBIGUOUS = re.compile(r'말고|아니|아닌|안\s*|않|없|못|싫|불필요|제외|빼|대신|또는|혹은|[?？]')
DATE_TOKEN = re.compile(
    r'(?<!\d)(?:(\d{4})-(\d{1,2})-(\d{1,2})|'
    r'(\d{4})/(\d{1,2})/(\d{1,2})|'
    r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일)(?!\d|[./-]\d)'
)
# Bound both ends so 113시 / 13:000 / 13:00:30 cannot become valid substrings.
TIME_TOKEN = r'(?<![\d:])(오전|오후)?\s*(\d{1,2})(?::(\d{2})|시(?:\s*(\d{1,2})분)?)(?![\d:])'
TIME_RANGE = re.compile(TIME_TOKEN + r'\s*부터\s*' + TIME_TOKEN + r'\s*까지')


def relevant_clauses(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [clause for clause in re.split(r'[,，。.!！\n]', text)
            if any(word in clause for word in keywords)]


def uncertain(clauses: list[str]) -> bool:
    return any(AMBIGUOUS.search(clause) for clause in clauses)


def parse_time(text: str) -> TimeRange | None:
    dates = list(DATE_TOKEN.finditer(text))
    hours = list(re.finditer(TIME_TOKEN, text))
    ranges = list(TIME_RANGE.finditer(text))
    if len(dates) != 1 or len(hours) != 2 or len(ranges) != 1:
        return None
    if uncertain([text]):
        return None
    values = []
    date = [int(value) for value in dates[0].groups() if value is not None]
    endpoints = ranges[0].groups()
    try:
        for period, hour, minute_colon, minute_word in (endpoints[:4], endpoints[4:]):
            h, m = int(hour), int(minute_colon or minute_word or '0')
            # Unmarked 1~11시 is ambiguous; HH:mm is an explicit 24h format.
            if period:
                if not 1 <= h <= 12:
                    return None
                h = h % 12 + (12 if period == '오후' else 0)
            elif not minute_colon and 1 <= h <= 11:
                return None
            values.append(datetime(*date, h, m, tzinfo=SEOUL))
    except ValueError:
        return None
    return TimeRange(*values) if values[0] < values[1] else None


class RuleBasedParser:
    def parse(self, text: str) -> Extraction:
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise ValueError('message must contain 1 to 1000 characters')
        result = Extraction({name: ExtractedCondition(None, 'UNSET',
                            'SOFT' if name in ('transport', 'indoor_preference', 'companions', 'preference_tags') else 'HARD')
                            for name in FIELDS})

        def assign(name, value, strength='HARD', source='USER'):
            result.conditions[name] = ExtractedCondition(value, source, strength)

        def mark(name):
            result.unconfirmed_fields.add(name)

        areas = relevant_clauses(text, ('해운대', '서면', '광안리', '남포', '서울', '부산 외'))
        if areas:
            if not uncertain(areas) and all('해운대' in c for c in areas) and not any(
                key in ' '.join(areas) for key in ('서면', '광안리', '남포', '서울', '부산 외')
            ):
                assign('area', 'HAEUNDAE')
            else:
                mark('area')

        time_mentions = re.search(r'\d\s*시|\d:\d|오늘|내일|오전|오후|저녁|아침|시간', text)
        if time_mentions:
            window = parse_time(text)
            if window:
                assign('time_window', window)
            else:
                mark('time_window')

        transport_map = {'도보': 'WALK', '걸어서': 'WALK', '대중교통': 'PUBLIC',
                         '지하철': 'PUBLIC', '버스': 'PUBLIC', '자차': 'CAR', '자동차': 'CAR'}
        transports = relevant_clauses(text, tuple(transport_map))
        choices = {v for k, v in transport_map.items() if k in text}
        if not transports:
            assign('transport', 'WALK', 'SOFT', 'DEFAULT')  # DEC-001 sprint 2.
        elif len(choices) == 1 and not uncertain(transports):
            hard = re.search(r'꼭|반드시|절대|도보만|걸어서만|대중교통만|지하철만|버스만|자차만|자동차만', ' '.join(transports))
            assign('transport', choices.pop(), 'HARD' if hard else 'SOFT')
        else:
            mark('transport')

        mobility_map = {'휠체어': 'WHEELCHAIR', '유모차': 'STROLLER', '부상': 'INJURY'}
        mobility = relevant_clauses(text, (*mobility_map, '다쳤', '아파', '불편', '계단'))
        mobility_values = tuple(dict.fromkeys(v for k, v in mobility_map.items() if k in text))
        if mobility:
            if mobility_values and not uncertain(mobility) and not any(
                k in ' '.join(mobility) for k in ('다쳤', '아파', '불편', '계단')
            ):
                assign('mobility', mobility_values)
            else:
                mark('mobility')

        companion_map = {'혼자': 'SOLO', '친구': 'FRIENDS', '연인': 'COUPLE', '가족': 'FAMILY'}
        companions = relevant_clauses(text, (*companion_map, '영유아', '아기', '아이', '명', '둘', '셋'))
        if companions:
            kinds = {v for k, v in companion_map.items() if k in text}
            counts = re.findall(r'(\d+)\s*명', text)
            infant = bool(re.search(r'(영유아|아기)', text))
            if not uncertain(companions) and len(kinds) <= 1 and len(counts) <= 1:
                kind = next(iter(kinds), None)
                count = int(counts[0]) if counts else (1 if kind == 'SOLO' else None)
                if count is not None and (count < 1 or (kind == 'SOLO' and count != 1)):
                    mark('companions')
                else:
                    assign('companions', CompanionHints(kind, count, True if infant else None), 'SOFT')
            else:
                mark('companions')

        # Do not invent amounts, exclusions or resolve negative language in this
        # skeleton. Mentioned but unsupported grammar requires confirmation.
        if re.search(r'예산|\d\s*원|만원|비용|무료', text):
            mark('budget')
        if re.search(r'빼|제외|가지\s*않|안\s*가', text):
            mark('excluded_categories')
        indoors = relevant_clauses(text, ('실내', '실외', '야외'))
        if indoors:
            if not uncertain(indoors) and '실내' in text and '실외' not in text and '야외' not in text:
                assign('indoor_preference', 'INDOOR', 'HARD' if re.search(r'꼭|절대|반드시|실내(?:에서)?만', ' '.join(indoors)) else 'SOFT')
            else:
                mark('indoor_preference')
        # No infant->stroller transform: pending USER/[] precedence (PR #13).
        # No READY/503, session updates, support checks or course generation.
        return result
