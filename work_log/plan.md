# newsmailing — 구현 계획

## Context

회사 내부용 뉴스 메일링 도구. 담당자가 브라우저에서 관심 키워드를 입력하면 Naver 검색 API로 최근 기사를 모아 보여주고, 담당자가 체크한 기사만 정리된 HTML 메일로 사내 수신자 리스트에 일괄 발송한다.

**해결하려는 문제**: 매일 키워드 20여 개에 대해 Naver 뉴스를 수동으로 확인 → 복사 → 메일 본문 구성 → 발송하는 반복 업무를 단일 화면으로 단축.

**의도한 결과물**: 로컬 또는 사내 서버에서 돌아가는 Flask 기반 웹앱. 키워드 입력 → 기사 후보 체크 → 메일 발송까지 한 화면에서 완결.

---

## 아키텍처 개요

```
[Browser UI]
  ├─ 키워드 입력 (쉼표 구분)
  ├─ [기사 찾기] → POST /api/search
  ├─ 후보 목록(체크박스, 제목, 출처, 링크, 날짜)
  ├─ 수신자 입력 (세미콜론 구분) / 제목 / (선택) 본문 서두
  └─ [메일 보내기] → POST /api/send

[Flask Backend]
  ├─ app.py            라우팅 (/, /api/search, /api/send)
  ├─ naver_client.py   Naver 검색 API 호출 + 필터/중복제거
  ├─ mailer.py         SMTP 발송 (HTML 본문 렌더)
  ├─ config.py         .env 로더
  └─ templates/index.html  단일 페이지 UI (Vanilla JS)

[Config / Secrets]
  └─ .env              NAVER_CLIENT_ID, NAVER_CLIENT_SECRET,
                       SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
                       SMTP_FROM, SMTP_USE_TLS
```

### 데이터 흐름

1. **검색**: 키워드별로 Naver News API 호출 (`sort=sim`, `display=30`) → `pubDate`가 어제/오늘인 항목만 필터 → 제목/요약 HTML 태그 제거 → URL(`originallink`) 기준 전역 중복 제거 → 키워드당 상위 3~5개 → 병합 반환.
2. **출처 추출**: Naver API는 출처명을 직접 주지 않음. `originallink` 도메인을 도메인→언론사 매핑 테이블로 변환. 매핑 없을 시 도메인 그대로 표시.
3. **발송**: 체크된 기사 JSON을 받아 HTML 테이블 생성 → `smtplib.SMTP`로 BCC 단일 발송.

---

## Phase 분할

각 Phase 완료 시 `work_log/Phase_XXX.md` 작성, 본 계획의 체크리스트 `[x]` 갱신, 테스트 agent 통과 후 다음 Phase 진행.

### Phase 001 — 프로젝트 스캐폴딩 / 환경 구성 ✅

- [x] `requirements.txt` 작성 (`flask`, `requests`, `python-dotenv`)
- [x] `.env.example` 작성 (실제 `.env`는 사용자가 채움)
- [x] `.gitignore` (`.env`, `__pycache__`, `venv/` 등)
- [x] 디렉토리 구조 생성: `app.py`, `config.py`, `templates/`, `static/`, `work_log/`
- [x] `config.py`: dotenv 로드 + 필수 환경변수 검증
- [x] `app.py` 최소 동작: `/` 라우트에서 "Hello" 반환 → 로컬 기동 확인

**완료 기준**: `python app.py` → `http://localhost:5000` 접속 시 응답 확인. (PASS, 2026-04-17)

### Phase 002 — Naver 검색 API 연동 ✅

- [x] `naver_client.py`: `search_news(query, display=30)` — 단일 키워드 호출
- [x] `parse_pubdate()`: RFC 822 형식 → `datetime` 변환
- [x] `filter_recent()`: 어제 00:00 ~ 오늘 현재까지만 남김 (KST 기준)
- [x] `strip_html()`: `<b>`, `&quot;` 등 Naver 응답의 HTML 엔티티/태그 정리
- [x] `extract_source()`: URL → 언론사명 (초기 매핑 30개 + 폴백)
- [x] `collect(keywords, per_keyword=5)`: 여러 키워드 병합, URL 기준 전역 중복 제거
- [x] 단위 테스트: 18/18 PASS, 실제 API 스모크 PASS

**외부 제약**:
- Naver 개발자 센터에서 앱 등록, "검색" API 사용 체크, Client ID/Secret 발급 필요 (사용자 작업)
- 일일 25,000회 호출 한도
- `display` 최대 100, `sort=sim` 또는 `date`
- Header: `X-Naver-Client-Id`, `X-Naver-Client-Secret`

**완료 기준**: 실제 키워드 1개 호출 → 어제/오늘만 필터링된 리스트 반환 확인.

### Phase 003 — 검색 UI ✅

- [x] `templates/index.html`: 단일 페이지
- [x] 기본 스타일 `static/style.css` — 테이블, 체크박스
- [x] `/api/search` (POST): `{keywords: string}` → `{articles: [...]}` JSON
- [x] 프론트 JS (Vanilla): fetch → 결과 렌더 (체크박스 + 제목 링크 + 출처 + 날짜)
- [x] 로딩/에러 status 표시

**완료 기준**: 브라우저에서 키워드 입력 → 목록이 체크박스와 함께 표시.

### Phase 004 — 메일 발송 ✅

- [x] `mailer.py`: `send(recipients, subject, articles, intro_text)`
- [x] HTML 템플릿: 인트로 + 기사 테이블(제목 링크 / 출처) + 푸터
- [x] SMTP 연결: TLS/SSL 여부 `.env` 분기, 인증 실패 시 명확한 에러
- [x] 수신자 처리: `;` 분리 → 공백/빈값 제거 → BCC 단일 발송
- [x] `/api/send` (POST): `{recipients, subject, intro, articles}` → `{success, sent_count, error?}`
- [x] 프론트: 체크된 항목 수집 → 발송 → 성공/실패 토스트

**외부 제약**:
- 회사 SMTP 호스트/포트/인증 방식 사전 확인 필요 (IT팀 문의 가능성)
- 외부 앱 발신 허용, 앱 비밀번호 필요 가능성
- 발신자(`SMTP_FROM`)가 인증 계정과 다르면 거부될 수 있음

**완료 기준**: 실제 SMTP로 본인 메일 1곳 테스트 발송 → 수신 + 링크 동작 확인.

### Phase 005 — 통합 / 마감 (범위 확장)

기본 계획 외 UX 개선 다수 추가. 상세 `work_log/Phase_005.md` 참조.

- [x] 에러 처리 정리 (Naver API / SMTP / 첨부 크기 413 핸들러)
- [ ] 수신자/키워드 이메일 정규식 유효성 검사 (이월)
- [ ] 도메인→언론사 매핑 확장 30→50개 (이월)
- [x] 매뉴얼 작성 (`manual.md` — README 대체, 운영 체크리스트 포함)
- [x] End-to-end 실 발송 검증 (pesseq@naver.com 정상, sec@vanasso.kr 스팸함 — DNS 별도 트랙)

**추가 구현 (계획 외)**:
- [x] UI 디폴트 (발신자명/이메일/제목/서두/서명) 자동 로드
- [x] 수신자 리스트 파일 지속화 (`data/settings.json`)
- [x] 미리보기 모달 + WYSIWYG 본문 편집
- [x] 스팸 대응 헤더 (Message-ID / Reply-To)
- [x] 기사 렌더 포맷 (표 제거, 짙은 갈색 볼드 밑줄 + 출처)
- [x] 기사 정렬 (키워드 순 × 게시 최신순)
- [x] 발신자 이메일 alias 지원
- [x] 첨부파일 (다중, 누적, 크기 제한)

### (선택적 확장) Phase 006 — LLM 기반 관련성 랭킹

초기 버전 사용 후 품질이 아쉬우면 추가. Naver 정확도순 결과(키워드당 10개 후보)를 Claude API로 넘겨 관련성 상위 3개 선택.

---

## 외부 제약 조건 (사용자 준비 사항)

1. **Naver 검색 API 키**: developers.naver.com → 애플리케이션 등록 → "검색" API 선택 → Client ID/Secret을 `.env`에 기입.
2. **회사 SMTP 정보**: 호스트, 포트, TLS/SSL 여부, 인증 계정/비밀번호, 발신자 주소.
3. **Python 3.10+** 환경. 가상환경 권장.

---

## 핵심 파일 목록

| 경로 | 역할 |
|---|---|
| `app.py` | Flask 엔트리, 라우팅 |
| `config.py` | `.env` 로드 및 검증 |
| `naver_client.py` | Naver 검색 API + 필터/중복제거 |
| `mailer.py` | SMTP HTML 메일 발송 |
| `templates/index.html` | 단일 페이지 UI |
| `static/style.css` | 기본 스타일 |
| `.env.example` | 환경변수 템플릿 |
| `.env` | 실제 시크릿 (gitignore) |
| `requirements.txt` | 의존성 |
| `work_log/plan.md` | 본 계획서 (체크박스 갱신) |
| `work_log/Phase_XXX.md` | Phase별 작업 로그 |

---

## 검증 방법 (End-to-End)

1. `.env` 작성 후 `python app.py` 기동.
2. `http://localhost:5000` 접속.
3. 키워드 3~5개 입력 → [기사 찾기] → 목록 표시.
4. 기사 체크 → 수신자에 본인 메일 → 제목 입력 → [메일 보내기].
5. 수신 확인, 제목 링크 클릭 동작.
6. 에러 케이스: 잘못된 SMTP 비밀번호 → UI 에러 표시.
