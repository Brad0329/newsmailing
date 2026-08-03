# Phase 006 — 검색 기간 / 기사 없이 발송 / 예약 발송

**완료일**: 2026-04-23
**상태**: 3개 기능 모두 구현 + 테스트 + 스모크 검증 완료. 실사용 E2E(실제 SMTP 예약 발송 트리거 시각 도달)는 사용자 현장에서 별도 확인.

## 결정의 이유

### 1. 검색 기간 — `<select>` 1~5일 (free date range picker 아님)
- 애초 제안은 `시작일/종료일` 두 개 input이었으나 Naver API가 날짜 파라미터를 지원하지 않아 **범위가 넓을수록 skip할 최신 기사가 늘어 호출 비용 증가**. 현실적으로 담당자가 쓰는 범위는 "오늘~최근 며칠" 수준이라 select 1~5로 제한.
- 상한 5일 + 페이지 상한 2 = 호출 비용 예측 가능(키워드당 최대 2회, 총 키워드수 × 2).
- 기본값 2 → 기존 "어제~오늘" 동작 그대로. 기존 사용자 경험 무붕괴.

### 2. `sort=sim` → `sort=date`로 변경 (collect 내부)
- 과거: `sort=sim`으로 30개 받은 뒤 어제/오늘 필터링 → "오늘 기준 시점에선 상위 30개 안에 어제~오늘 기사가 충분히 많으니 OK"라는 전제.
- 현재: 날짜 범위가 선택 가능해지면서 API 결과 정렬을 `date`로 바꿔야 **조기 종료 최적화**(pub_date < range_start 도달 시 break) 가능. sim 순서면 중간에 오래된 기사가 섞여 조기 종료 불가.
- 트레이드오프: 관련도 정렬을 잃지만 현재 로직은 어차피 "범위 내 최신순"을 원하므로 date가 더 적합.

### 3. 페이지 상한 2 × display 30 = 60건
- 사용자 의견 반영 (display=100이 비용면에서 유리하지만 단일 페이지로는 관련도 낮은 말단까지 한 번에 받는 걸 부담스러워함).
- 수집 5개 기준, 60건 안에 충분히 5개 매치됨. 범위가 과도하게 넓거나 키워드가 드문 경우 2페이지로도 부족할 수 있지만 그 경우 매뉴얼로 대응.

### 4. 기사 없이 발송 — `render_body_fragment` 빈 섹션 생략
- 기존: `articles`가 비면 `<p>기사 없음</p>` 출력 → 메일에 어색한 문구 남음.
- 현재: 빈 기사 섹션은 통째로 생략, 인트로 + 서명(+ 사용자가 편집기에서 직접 쓴 본문)만으로 자연스러운 메일.
- 서버 검증도 완화: `/api/preview`, `/api/send` 모두 `articles: []` 허용. 버튼 활성화 검증도 프론트에서 제거.

### 5. 예약 발송 — APScheduler + 파일 기반 영속화 (DB 없음)
- **jobstore 선택지**: MemoryJobStore (기본), SQLAlchemyJobStore(SQLite). SQLAlchemy 의존 추가 부담 + 단일 사용자 규모에서는 과한 복잡도.
- 선택: **MemoryJobStore + 파일 기반 자체 영속화**. `data/scheduled/<id>/`에 meta.json + attachments. 앱 시작 시 `init()`이 디스크를 스캔해 pending 중 미래분만 APScheduler에 재등록. 과거분은 `status=missed`로 마킹(자동 발송 안 함).
- 파일이 단일 진실 — APScheduler는 "이번 세션 동안 발사할 알람" 역할만. 재기동 시에도 상태 일관성 유지.

### 6. 놓친 예약은 자동 발송 금지 (missed)
- 예약 시각이 지나서 앱이 켜졌을 때 자동으로 발송하면 의도치 않은 결과(이미 다른 경로로 발송됐을 수도, 시의성 지난 내용 등) 위험.
- `status=missed`로 기록만 하고 UI에 표시 → 사용자가 내용 확인 후 재발송 여부 판단. 안전 우선 정책.
- APScheduler의 `misfire_grace_time=300`은 트리거 발사는 됐는데 실행이 조금 늦어진(<5분) 경우에만 동작. 앱이 아예 꺼져 있던 경우엔 해당 없음.

### 7. Flask debug reloader 이중 시작 방지
- Flask 디버그 모드는 부모/자식 2개 프로세스를 띄움 → `scheduler.init()`을 모듈 import 시에 호출하면 2번 실행돼 작업 중복.
- 해결: `app.py`에서 자동 시작하지 않고 `start_scheduler()` 별도 함수로 뽑음. `if __name__ == "__main__":` 안에서 `WERKZEUG_RUN_MAIN == "true"` 또는 non-debug일 때만 호출. `run.py`(waitress)는 환경변수 없이 무조건 호출. 테스트 import 시에는 자동 시작 안 됨 → 격리 용이.

### 8. 발신 시각 파싱 — `datetime-local`은 타임존 미포함
- 브라우저 `<input type="datetime-local">`의 value는 `YYYY-MM-DDTHH:MM` (타임존 없음).
- 서버에서 `datetime.fromisoformat(...)` 후 tzinfo가 없으면 **KST로 해석** (운영 전제: 사용자는 한국 시각으로 입력).
- 그 결과 ISO 저장본은 항상 `...+09:00` 포함 → 재로드/재등록 시 혼동 없음.

### 9. envelope 파일 저장/재로드 전략 — html_fragment를 사용자 편집본 그대로 저장
- 예약 생성 시점에 `preview-editor`에서 사용자가 편집한 HTML을 그대로 meta.json에 넣음.
- 실행 시에는 그 HTML을 `wrap_document`로 감싸 발송. 예약과 즉시 발송의 렌더 일관성 유지.
- 첨부파일은 바이너리 그대로 보존. 디스크 파일명은 `<idx>_<sanitized>` 포맷으로 충돌 회피.

## 외부 제약 조건 (운영 메모)

- **앱 상주 필요**: 예약 시각에 newsmailing.exe가 실행 중이어야 발송됨. exe가 꺼진 동안 지나간 예약은 다음 기동 시 `missed` 표시 — 자동 발송 안 함.
- **단일 프로세스**: 스케줄러는 Flask/waitress 서버 프로세스 내부에 살아 있음. 같은 data 폴더를 가리키는 exe를 2개 동시에 띄우면 예약이 중복 실행될 수 있음. 1개만 기동 원칙.
- **예약 데이터 위치**: `data/scheduled/<id>/`. 실수로 지우면 해당 예약 소실. 백업 대상.
- **예약 삭제**: UI의 "삭제" 버튼은 폴더 전체 제거. pending/missed/failed 어떤 상태든 제거.
- **시간대**: 저장/표시 모두 KST. 입력(datetime-local)도 KST로 해석. 해외 타임존 사용 시 의도와 다르게 저장될 수 있음.
- **첨부 총 크기**: `/api/schedule`도 `/api/send`와 동일하게 25MB 제한 적용 (`MAX_CONTENT_LENGTH`).
- **설정 파일 저장 시점**: 예약 성공 시점에도 `storage.save_recipients`/`save_mail_fields` 호출 — 즉시 발송과 동일하게 디폴트 갱신. 취소해도 저장분은 남음(사용자 편의성 우선).

## 실패한 접근 / 이슈

### `sort=date` 페이지네이션 중 최신 기사 중복
- Naver API는 실시간 색인 업데이트 → 페이지 1 호출 직후 새 기사가 들어오면 페이지 2의 첫 항목이 페이지 1 말미와 겹칠 수 있음.
- 대응: `seen_urls` set으로 URL 전역 중복 제거(기존 로직 유지). 중복 문제 없음.

### APScheduler 반복 import 시 경고
- 테스트/스모크에서 `scheduler.init()` 연속 호출 시 "scheduler already running" 무시 처리. `_get_scheduler()`는 lock + singleton. 안전.

### Flask test_client에서 `/api/schedule`이 실제 APScheduler 등록까지 수행
- 스모크 테스트 후 취소하지 않으면 실제 스케줄이 백그라운드에 남음. 테스트에서는 항상 `delete` 호출로 정리. 실운영엔 영향 없지만 CI 추가 시 fixture로 teardown 필요.

## 추가 구현 세부

### 파일 추가/수정
- **추가**: `scheduler.py`
- **수정**: `storage.py`(예약 CRUD), `naver_client.py`(`collect(days=)` + `search_news(start=)`), `app.py`(라우트 3개 + 공통 파서), `run.py`(start_scheduler 호출), `templates/index.html`(select + 모달 스케줄 컨트롤 + 목록 섹션), `static/style.css`(스타일), `requirements.txt`(apscheduler 추가)

### API
- `POST /api/schedule` — 예약 생성 (즉시 발송과 동일 payload + `scheduled_at`)
- `GET /api/scheduled` — 모든 예약 목록 (pending/missed/failed 모두)
- `DELETE /api/scheduled/<id>` — 예약 취소

### UI
- 검색 섹션: "검색 기간" `<select>` (오늘만 / 어제~오늘 / 최근 3~5일)
- 미리보기 모달 footer 위: `[즉시 발송 ○] [예약 발송 ○] [datetime-local]` + 경고 힌트
- 모달 열릴 때마다 즉시 모드로 리셋 (의도치 않은 예약 방지)
- 새 카드 섹션 "예약된 발송" — 시각 / 제목 / 수신자 수 / 첨부 수 / 상태 배지 / 삭제 버튼

## 향후 운영상 주의점

- **재시작 후 missed 쌓임**: 오래 꺼뒀다가 켜면 missed 가 누적됨. UI에서 missed는 삭제 버튼으로 직접 정리. 자동 정리는 의도적으로 미구현 — 사용자가 "놓쳤다"는 사실을 인지해야 함.
- **예약 취소 후 재발송**: 현재 UI는 취소만 — 재사용 편집 기능 없음. 필요하면 future Phase.
- **매뉴얼 갱신 필요**: `manual.md`에 "예약 발송 사용법"과 "앱 상주 필요" 조항 추가 (이월).
- **빌드 시**: `data/scheduled/` 폴더는 런타임 생성물이므로 `.gitignore` 대상 (추가 예정). 빌드 번들에 포함 안 함.

## 테스트 결과

- naver_client 단위 테스트: 18/18 PASS (기존 통과 로직 무붕괴)
- 모듈 import: `app`, `scheduler`, `storage` 모두 import OK
- storage 예약 CRUD: 생성 → 로드 → 첨부 로드 → 삭제 전 과정 동작 확인
- scheduler 시작/종료: running 플래그 / shutdown 정상
- Flask test_client:
  - `/api/search` (keywords 빈 값 → 400)
  - `/api/scheduled` (빈 목록 정상 반환)
  - `/api/schedule` 미래 시각 → 200, 목록에 등록 → DELETE로 제거
  - `/api/schedule` 과거 시각 → 400 거부
