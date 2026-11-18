"""Repository-only detail query; never invokes a model or changes sessions."""
from uuid import uuid4
from fastapi import APIRouter, Request, Response
from app.api.errors import error_response
from app.api.place_models import PlaceResponse
from app.places.presentation import place_payload, source_payloads, warning

router = APIRouter()


@router.get('/api/places/{placeId}', response_model=PlaceResponse)
def get_place(placeId: str, request: Request, response: Response):
    repository = request.app.state.place_repository
    if repository is None:
        return error_response(500, 'INTERNAL_ERROR', '장소 조회 연결이 준비되지 않았어요.', True)
    try:
        record = repository.get_place(placeId)
        if record is None:
            return error_response(404, 'NOT_FOUND', '요청한 장소를 찾지 못했어요.')
        if record.id != placeId:
            raise ValueError('repository ID mismatch')
        place = place_payload(record)
        warnings = [warning('DATA_NOTICE', '공공데이터 정보는 실제 현황과 다를 수 있어요. 방문 전 확인해 주세요.', [record.id]),
                    warning('PRICE_UNKNOWN', '가격 정보를 확인할 수 없어요.', [record.id])]
        if place['openHours']['status'] == 'UNKNOWN':
            warnings.append(warning('OPEN_HOURS_UNKNOWN', '운영시간을 확인할 수 없어요. 원문이 있어도 영업 중임을 보장하지 않아요.', [record.id]))
        if place['accessibility']['grade'] == 'UNKNOWN':
            warnings.append(warning('ACCESSIBILITY_UNKNOWN', '접근성 정보가 충분하지 않아요.', [record.id]))
        model = PlaceResponse(place=place, sources=source_payloads(repository, record.source_ids),
                              warnings=warnings, requestId=uuid4())
    except Exception:
        # Storage errors and invalid stored records are failures, never 404/empty success.
        # Do not let dependency exception text reach logging middleware.
        return error_response(500, 'INTERNAL_ERROR', '장소 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.', True)
    response.headers['Cache-Control'] = 'no-store'
    return model
