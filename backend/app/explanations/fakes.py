"""Explicit synthetic fact selector; never calls a real model or retains context."""
import json


class SyntheticExplanationProvider:
    async def complete(self, request):
        return json.dumps({'items': [{'placeId': place.place_id, 'facts': ['CATEGORY', 'STAY']}
                                     for place in request.context.places]})
