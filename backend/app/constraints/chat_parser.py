"""Small explicit chat grammars on top of the conservative fallback skeleton."""
import re

from app.constraints.parser import RuleBasedParser, relevant_clauses
from app.domain.extraction import ExtractedCondition, CompanionHints


class ChatRuleParser(RuleBasedParser):
    def parse(self, text):
        # The PM evaluation set explicitly labels its synthetic inputs.
        if isinstance(text, str):
            text = re.sub(r'^\s*\[가상\]\s*', '', text)
        result = super().parse(text)

        def assign(name, value, strength='HARD'):
            result.conditions[name] = ExtractedCondition(value, 'USER', strength)
            result.unconfirmed_fields.discard(name)

        # Accept only whole, explicit clauses. Mixed/negated requests stay pending.
        for clause in relevant_clauses(text, ('실내', '실외', '야외')):
            clause = clause.strip()
            if re.fullmatch(r'(실외|야외)(?:는|은)?\s*(?:절대\s*)?(?:안\s*돼|안\s*됨|못\s*가|싫어)(?:요)?', clause):
                if len(relevant_clauses(text, ('실내', '실외', '야외'))) == 1:
                    assign('indoor_preference', 'INDOOR')

        exclusions = relevant_clauses(text, ('빼', '제외'))
        categories = {'카페': 'CAFE', '음식점': 'FOOD', '전시': 'EXHIBITION',
                      '관광지': 'ATTRACTION', '공원': 'PARK', '쇼핑': 'SHOPPING'}
        if exclusions:
            values = []
            for clause in exclusions:
                match = re.fullmatch(r'\s*(' + '|'.join(categories) + r')(?:는|은|을|를)?\s*(?:빼\s*줘|제외해\s*줘)(?:요)?\s*', clause)
                if not match:
                    break
                values.append(categories[match[1]])
            else:
                assign('excluded_categories', tuple(dict.fromkeys(values)))

        injury_clauses = relevant_clauses(text, ('다쳤', '아파', '부상'))
        if (injury_clauses == relevant_clauses(text, ('휠체어', '유모차', '다쳤', '아파', '부상', '불편', '계단'))
                and injury_clauses and all(re.fullmatch(
            r'\s*(?:(?:다리|발목|무릎)(?:가|을|이)?\s*)?(?:다쳤어|다쳤어요|아파|아파요|부상)(?:요)?\s*', c
        ) for c in injury_clauses)):
            existing = result.conditions['mobility'].value or ()
            assign('mobility', tuple(dict.fromkeys((*existing, 'INJURY'))))

        companion = result.conditions['companions'].value
        if isinstance(companion, CompanionHints) and '아이' in text:
            assign('companions', CompanionHints(companion.type, companion.count, companion.has_infant, True), 'SOFT')
        if re.fullmatch(r'\s*(?:아기|영유아)(?:는|가|를)?\s*(?:없어요|없어|동반하지 않아요)\s*[.!]?\s*', text):
            assign('companions', CompanionHints(has_infant=False), 'SOFT')
        return result
