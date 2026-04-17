# Phase 005 — UX 개선 (대규모 확장)

**완료일**: 2026-04-17
**상태**: 원래 계획(에러 정리/매핑 확장/README/E2E)보다 훨씬 큰 UX 개선이 이어지면서 Phase 005 범위가 확장됨. 핵심 기능은 모두 구현·검증 완료. 일부 마감 항목은 실사용 테스트 피드백 후로 이월.

## 결정의 이유

### 1. 디폴트 값 중앙화 — `defaults.py` 신설
- 제목/서두/서명/발신자명을 사용자 화면 디폴트로 요구 → 코드에 상수로 두고 `/api/settings`에서 주입.
- 이유: `.env`는 시크릿 전용. 운영 디폴트 텍스트는 시크릿이 아니므로 구분해 관리해야 변경 이력 추적이 쉬움.
- 트레이드오프: 디폴트 변경은 코드 수정 + 재빌드 필요. 운영 중 자주 바꿀 일은 없어 감수.

### 2. 수신자 리스트 지속화 — `storage.py` + `data/settings.json`
- 발송 성공 시 현재 textarea 내용을 그대로 저장. 페이지 로드 시 로드.
- "발송 시점 = 커밋 시점"으로 한정 — 편집 중 반쯤 날아간 상태가 저장되는 사고 방지.
- DB 없이 단일 JSON 파일로 충분 (사용자 1~2명, 리스트 수십 개).

### 3. 미리보기 → WYSIWYG 편집 전환
- 초기엔 단순 미리보기(iframe)였으나 사용자가 "본문 편집 가능" 요청 → `contenteditable` div로 교체.
- `render_body_fragment()` / `wrap_document()` 분리: 편집용 fragment와 실제 메일용 full HTML을 구분. 편집된 내용을 `html_fragment`로 서버에 전송 → 서버는 full document로 래핑하여 발송.
- iframe 대비 장점: 부모 페이지에서 DOM 접근/편집 내용 캡처 용이. 단점: 스타일 격리 없음(CSS 내부 누출) → 인라인 스타일만 사용해 해결.

### 4. 기사 렌더 포맷 — 표 → 자연스러운 `<p>` 리스트
- "사람이 쓴 것 같은" 느낌 요구 → 표(`<table>`) 제거, 제목+링크+`/`+출처의 단일 문장 행.
- 제목은 짙은 갈색(#5D4037) + 볼드 + 밑줄 — 고유 브랜딩성 스타일.
- 스팸 필터 관점에서도 표 중심 구조는 템플릿 스팸으로 오인되기 쉬움 — 사이드 효과로 스팸 점수 감소 기대.

### 5. 스팸 대응 헤더
- `Message-ID` 명시 (`make_msgid(domain=...)`)
- `Reply-To` = From 주소
- 이유: Message-ID 미설정은 스팸 필터의 흔한 트리거. From/Reply-To 일치는 정상 메일의 기본 특성.
- 근본 해결은 DNS(SPF/DKIM/DMARC)이므로 코드만으로는 한계 있음 — `manual.md`에 DNS 가이드 기록.

### 6. 발신자 이름 + 이메일 주소 분리
- 표시명(display name)과 실 이메일 주소를 UI에서 각각 설정 가능.
- 환경 제약: SMTP 서버(hiworks)가 인증 계정과 다른 From 주소를 허용해야 함(alias/대리발신 권한).
- 구현 원칙: **envelope MAIL FROM은 항상 `SMTP_FROM`(인증 계정)**으로 고정 — 바운스 경로 및 SPF 정합성 유지. 헤더 `From`만 사용자가 지정한 주소로 변경.

### 7. 기사 정렬 — 키워드 순 × 게시 최신순
- 사용자 입력 키워드 순서를 최상위 그룹으로 유지 (담당자가 중요 키워드를 앞에 놓는 관행 반영).
- 그룹 내부는 pub_date desc — "최신 정보가 위" 관행.
- 관련성(`sort=sim`)은 Naver API에서 이미 후보군 필터링에 사용되므로 중복 정렬 불필요.

### 8. 첨부파일 기능
- `<input type="file" multiple>` + 누적 추가/개별 삭제.
- 전송: JSON 대신 multipart/form-data (첨부 있을 때만).
- 서버: `MAX_CONTENT_LENGTH=25MB` + 413 핸들러로 친화적 에러.
- `msg.add_attachment()` + `mimetypes.guess_type()`로 자동 Content-Type.

## 외부 제약 조건 (운영 메모)

- **SMTP alias 권한**: 발신 이메일 주소 변경은 hiworks 관리자 콘솔에서 해당 alias를 인증 계정에 연결해야 함. 실패 시 550 에러. 대안으로 Reply-To만 바꾸는 방식도 가능.
- **첨부 크기**: 현재 서버 제한 25MB. hiworks 메일 자체 제한은 보통 10~25MB (계정 등급에 따라 다름). 수신자 메일 서버(Gmail 25MB, Outlook 20MB 등)의 최소치에 맞춰야 안전.
- **첨부 파일명 인코딩**: Python `EmailMessage.add_attachment(filename=...)`는 RFC 2231 자동 인코딩. 한글/공백 파일명 OK. 단, 수신자 메일 클라이언트 호환성을 위해 가능하면 영문+숫자 권장.
- **WYSIWYG 편집 내용 처리**: 사용자가 편집한 HTML은 그대로 메일로 발송. 외부 사이트에서 복붙 시 인라인 스타일 유실/과다 가능성 있음 — 운영 가이드에 "plain text 형태로 붙여넣기" 권장.
- **수신자 저장 시점**: 발송 성공 직후. 발송 중 중단되면 저장 안 됨.
- **data/ 폴더 백업**: settings.json은 수신자 리스트 백업 대상.

## 실패한 접근 / 이슈

### 실제 SMTP 발송 1차 타임아웃 (Phase 004에서 이월된 재발 방지)
- 원인: `SMTP_PORT=465` + `SMTP_USE_TLS=true` 미스매치
- 해결: `.env`에서 `SMTP_USE_TLS=false`
- **향후 예방**: 변수명을 `SMTP_USE_STARTTLS`와 `SMTP_USE_SSL`로 분리하는 리팩터 보류 — 사용자 경험에 영향 없으므로 추후 리팩터로.

### 스팸함 도착 (sec@vanasso.kr)
- Phase 004 테스트에서 발송 자체는 성공했으나 수신 측이 스팸 처리.
- 원인: 같은 도메인 내 발송인데 DNS(SPF/DKIM/DMARC) 미설정 → 수신 필터가 "위장 가능성" 판정.
- 코드 대응: Message-ID / Reply-To / 표 제거 / 자연스러운 본문 (완화 효과만 있음)
- 근본 대응: 도메인 관리자/hiworks 관리 콘솔에서 SPF/DKIM 설정 필요 — 별도 트랙.

### Flask 재시작 필요 이슈
- 새 모듈(`defaults.py`, `storage.py`, `mailer` 시그니처 변경 등) 추가 시 Flask debug reloader가 일부 반영을 놓침.
- 해결: 주요 변경 시 preview 서버 수동 재시작. 최종 운영 배포(exe)에서는 waitress 사용으로 이슈 없어짐.

### sender_name 반영 누락 오해
- 사용자가 "여전히 newsmailing으로 수신"이라 보고 → 사실은 변경 **이전** 발송분이었음.
- 교훈: 코드 변경 후에는 확실히 서버 재시작 + 브라우저 하드 리프레시(Ctrl+F5)를 사용자에게 안내해야 함.

## 향후 운영상 주의점 (manual.md 요약)

- **.env와 data/settings.json은 백업**. 실수로 삭제하면 시크릿/수신자 리스트 손실.
- **포트와 TLS 매핑**은 `.env`에서 자주 틀리는 부분 — 465↔false, 587↔true.
- **Windows Defender/백신 오탐** 가능성 (PyInstaller 빌드물) — IT팀 화이트리스트 필요.
- **스팸 문제 재발 시 우선 확인 순서**:
  1. 수신자 메일 클라이언트가 스팸함으로 분류했는지
  2. `admin@vanasso.kr` 수신함에 바운스 메일이 왔는지
  3. DNS 레코드(SPF/DKIM/DMARC) 상태 (https://mxtoolbox.com 등 활용)
- **첨부파일 시**: 총 크기 25MB 초과 시 서버가 413으로 거부. 25MB는 서버 설정값이며, 수신측 제한에 맞춰 낮출 수 있음.

## 이월(마감 보류) 항목

원 Phase 005 계획 중 아래는 실사용 테스트 피드백 후 처리 예정:
- 언론사 도메인 매핑 추가 확장 (현재 30개 → 목표 50개 이상)
- 이메일 주소 정규식 유효성 검사 (현재는 형식 검증 없음)
- E2E 테스트 자동화 (현재 단위 테스트 + 수동 E2E)
- `SMTP_USE_TLS` 변수명 개선 리팩터
- 도메인 매핑에서 누락된 서브도메인 케이스 추가

## 추가로 작성된 산출물

- **`manual.md`** (루트): 담당자용 사용 매뉴얼 — 설치/`.env`/Naver 키 발급/일일 작업 흐름/트러블슈팅/운영 체크리스트 포함. 원 계획의 README 대체.
- **아이콘**: `data/vansso.png` — 추후 PyInstaller 빌드 시 `.ico` 변환 후 사용.

## 테스트 결과 요약

- 단위 테스트: `tests/test_naver_client.py` 18/18 + `tests/test_mailer.py` 6/6 = 24/24 PASS (최종 mailer 변경에 따라 일부 갱신 필요)
- 브라우저 자동화 검증 (preview_eval):
  - 디폴트 로드 (제목/서두/서명/발신자명/발신자이메일) OK
  - 검색 → 기사 리스트 (키워드 × 최신순) OK
  - 미리보기 모달 열림/편집 가능 OK
  - 첨부 파일 2개 추가/제거 OK
- 실 SMTP 발송: Phase 004에서 PASS (sent_count=2). sender_name 포함 재발송 PASS.
- 수신 측 스팸 이슈 잔존 — 코드 외 DNS 작업 필요.
