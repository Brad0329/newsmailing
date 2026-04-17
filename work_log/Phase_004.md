# Phase 004 — 메일 발송

**완료일**: 2026-04-17
**상태**: 테스트 통과 (단위 6/6, API 에러 케이스 3/3, 실발송 PASS)

## 결정의 이유

- **BCC 단일 발송 (vs 수신자별 루프)**: 수십 명 규모라 단일 발송이 성능·SMTP 연결 수·스팸 필터링 모두 유리. 수신자 주소가 서로 노출되지 않는 부가 이점.
- **`To:`는 발신자 본인, 실제 수신자는 `BCC`**: 완전 BCC만 쓰면 일부 메일 클라이언트/스팸 필터가 의심. 자기 자신을 To로 두는 관행을 따름.
- **`EmailMessage.set_content()` + `add_alternative(subtype='html')`**: 텍스트/HTML 멀티파트. HTML 미지원 클라이언트(드물지만) 또는 미리보기에서도 읽기 가능.
- **HTML은 테이블 인라인 스타일**: 메일 클라이언트(특히 Outlook, Naver 메일)는 외부 CSS/`<style>` 태그 지원이 불안정. 인라인 스타일만 허용.
- **발송 전 `confirm()` 다이얼로그 + JS escape**: 프론트에서 수십 명에게 한 번에 나가는 사고를 막는 최소 장치. HTML 본문에 사용자 입력이 들어가므로 `html.escape(quote=True)`로 양쪽(제목·URL·출처·intro) 모두 이스케이프.

## 외부 제약 조건 (운영 메모)

- **SMTP 포트와 TLS 플래그 매핑** (hiworks 기준, 다른 서버도 유사):
  - **465**: 직접 SSL 연결 — `.env`에 `SMTP_USE_TLS=false` 필요 (코드에서 `smtplib.SMTP_SSL` 경로)
  - **587**: STARTTLS — `.env`에 `SMTP_USE_TLS=true` 필요 (코드에서 `smtplib.SMTP` + `starttls()`)
  - 잘못 조합하면 연결이 바로 끊기고 "Connection unexpectedly closed: timed out" 타임아웃으로 표면화.
- **`SMTP_FROM` = 인증 계정과 일치 권장**: SPF/DKIM을 우회해 다른 주소로 발송 시도 시 hiworks 같은 일반 SMTP 서버는 거부함.
- **발송 주소 표기**: `From: newsmailing <admin@vanasso.kr>` 형태로 발신자명을 친근하게 — `email.utils.formataddr()` 사용.

## 실패한 접근 / 이슈

- **초회 실발송 타임아웃**: 원인 = `SMTP_PORT=465` + `SMTP_USE_TLS=true` 미스매치. `SMTP_USE_TLS=false`로 수정 후 성공. 같은 실수 재발 방지용으로 향후 변수명을 `SMTP_USE_STARTTLS` + `SMTP_USE_SSL`로 분리하는 개선 제안(Phase 005 리팩터 후보).
- **테스트 agent 1차 시도에서 curl 인라인 한글 JSON이 깨져 400 반환**: 서버 문제 아님. 파일 기반 POST로 해결. 운영 단계에서 curl 디버깅 시 `--data-binary @file.json` 패턴 권장.

## 향후 운영상 주의점

- **대량 발송 한도**: hiworks의 1회 발송 수신자 수/시간당 한도는 요금제 따라 다름. 수십 명 이하면 문제 없지만 수백 명 이상으로 늘 경우 분할 발송 로직 필요.
- **스팸/차단 리스크**: 동일 HTML 템플릿 반복 발송은 스팸 점수 상승 요인. 매일 다른 기사 세트로 나가는 구조라 크게 우려는 없으나, 수신자 불만 신고 1~2건으로도 도메인 평판 하락 가능 — 수신 동의 관리 필요.
- **발송 실패 시 재시도 없음**: SMTP 에러를 그대로 표시만 함. 운영에서 일부 수신자 거부(invalid mailbox) 상황 발생하면 로그만 남고 배치가 전체 실패하므로, Phase 005에서 개별 재시도 또는 bounce 리포트 고려.
- **비밀번호 특수문자**: `.env`에 `&&` 등이 포함된 비밀번호가 있음. dotenv 파싱은 문제없으나 쉘에 `source .env`로 로드하지 말 것 (`&&`가 명령 구분자로 해석됨). 항상 Python `python-dotenv`를 통해서만 로드.

## 테스트 결과 요약

- 단위 테스트: `tests/test_mailer.py` 6/6 PASS
  - `parse_recipients` 기본/공백/빈값
  - `_render_html` 내용 포함 + XSS escape
  - `_render_text` 포맷
- API 에러 케이스 3/3 PASS (빈 articles / 빈 recipients / 빈 subject → 400)
- 실발송 재테스트 PASS: `sent_count: 2` (pesseq@naver.com, sec@vanasso.kr)
