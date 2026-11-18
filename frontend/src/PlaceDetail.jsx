import './PlaceDetail.css'

const accessibilityLabels = {
  VERIFIED: '확인됨',
  UNKNOWN: '정보 없음',
  UNSUITABLE: '부적합',
}

function formatAvailability(value, yesLabel = '있음', noLabel = '없음') {
  if (value === true) return yesLabel
  if (value === false) return noLabel
  return '정보 없음'
}

export default function PlaceDetail({ detail, courseItem, isMock }) {
  const { place, sources, warnings } = detail
  const accessibility = place.accessibility
  const hasDataNotice = warnings.some((warning) => warning.code === 'DATA_NOTICE')

  const openingHours = place.openHours?.status === 'KNOWN'
    ? place.openHours.description ?? '정보 없음'
    : '정보 없음'

  const stayTime = courseItem?.stayMinutes == null
    ? '정보 없음'
    : `${courseItem.stayMinutes}분`

  return (
    <section className="condition-card place-detail" aria-label="장소 상세">
      <header className="place-detail-header">
        <h3>{place.name}</h3>
        {isMock && <span className="place-detail-badge">가상 응답</span>}
      </header>

      <dl className="place-detail-facts">
        <dt>주소</dt>
        <dd>{place.address ?? '정보 없음'}</dd>

        <dt>운영시간</dt>
        <dd>{openingHours}</dd>

        <dt>코스 체류시간</dt>
        <dd>{stayTime}</dd>
      </dl>

      <div className="place-detail-reason">
        <h4>추천 이유</h4>
        <p>{courseItem?.reason ?? '정보 없음'}</p>
      </div>

      <div className="place-detail-group">
        <h4>접근성</h4>
        <dl className="place-detail-facts">
          <dt>접근성 등급</dt>
          <dd>{accessibilityLabels[accessibility?.grade] ?? '정보 없음'}</dd>

          <dt>휠체어 이용</dt>
          <dd>{formatAvailability(accessibility?.wheelchair, '가능', '불가')}</dd>

          <dt>유모차 이용</dt>
          <dd>{formatAvailability(accessibility?.stroller, '가능', '불가')}</dd>

          <dt>엘리베이터</dt>
          <dd>{formatAvailability(accessibility?.elevator)}</dd>

          <dt>장애인 화장실</dt>
          <dd>{formatAvailability(accessibility?.accessibleToilet)}</dd>
        </dl>
      </div>

      <div className="place-detail-group">
        <h4>데이터 출처</h4>
        {sources.length === 0 ? (
          <p>정보 없음</p>
        ) : (
          <ul className="place-detail-sources" role="list">
            {sources.map((source) => (
              <li key={source.id}>
                <dl className="place-detail-facts">
                  <dt>제공기관</dt>
                  <dd>{source.provider ?? '정보 없음'}</dd>

                  <dt>데이터명</dt>
                  <dd>{source.datasetName ?? '정보 없음'}</dd>

                  <dt>기준일</dt>
                  <dd>{source.baseDate ?? '정보 없음'}</dd>

                  <dt>이용조건</dt>
                  <dd>{source.license ?? '정보 없음'}</dd>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="place-detail-notices">
        {warnings.map((warning) => (
          <p key={warning.code}>{warning.message}</p>
        ))}
        {!hasDataNotice && (
          <p>공공데이터 정보는 실제 운영 상황과 다를 수 있어요.</p>
        )}
      </div>
    </section>
  )
}