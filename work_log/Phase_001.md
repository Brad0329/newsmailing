# Phase 001 — 프로젝트 스캐폴딩 / 환경 구성

**완료일**: 2026-04-17
**상태**: 테스트 통과 (PASS)

## 결정의 이유

- **Flask 선택 (vs FastAPI)**: 단일 화면의 간단한 CRUD에 가까운 구조. 동기 I/O로 충분하고 템플릿 렌더/정적 파일까지 한 프레임워크로 처리 가능. FastAPI는 async 이점이 크지 않은 규모.
- **Vanilla JS (vs React/Vue)**: 페이지 하나, 상태도 단순(후보 리스트 + 체크). 빌드 툴체인/node_modules 없이 배포 단순화.
- **시크릿은 `.env` 파일 (vs 관리 UI)**: 사용자가 CLAUDE 대화에서 ".env 로컬 저장"을 명시 선택. 브라우저 전송 없음, 서버 프로세스만 접근.
- **`config.py`에서 `required=False` 기본값**: 검증을 호출 시점(`check_naver()`, `check_smtp()`)으로 미룸 — 이렇게 해야 Naver 키 없어도 앱 기동/정적 페이지 접근이 가능하며, 개발 중 부분 테스트가 수월.

## 외부 제약 조건 (운영 메모)

- **Python 3.10+ 필수**: `config.py`에서 `str | None` 유니온 문법 사용. 사용자 환경은 3.11.2로 확인됨.
- **`.env` 파일은 git 추적 제외**: `.gitignore`에 포함. 시크릿 유출 방지.
- **Flask 기본 바인딩 `127.0.0.1`**: 로컬 전용. 사내 서버 배포 시 `FLASK_HOST=0.0.0.0`으로 변경하고 방화벽/역프록시 정책을 별도 검토 필요.
- **디버그 모드 기본 `true`**: 개발 편의용. **운영 배포 시 반드시 `FLASK_DEBUG=false`로 변경** — 디버그 모드는 임의 코드 실행 가능 취약점이 있음.

## 실패한 접근 / 이슈

- 없음. 첫 통합 테스트에서 전 항목 PASS.

## 향후 운영상 주의점

- `.env` 파일은 서버에만 존재해야 하며, 백업/공유 시 제외.
- Flask 내장 서버는 개발용. 사내 서버 배포 시 `waitress` 또는 `gunicorn`(Linux) 등 WSGI 서버로 감싸는 것을 Phase 005 이후에 검토 필요. (Windows면 `waitress` 권장)
- 이 시점에는 의존성이 Flask/requests/python-dotenv 3개뿐 — 버전 업데이트 시 호환성 부담 낮음.

## 테스트 결과 요약

테스트 agent 리포트 전 항목 PASS:
- requirements.txt, .env.example, .gitignore 내용 검증
- templates/, static/, work_log/ 디렉토리 존재
- `pip install -r requirements.txt` 성공
- `.env` 없이 `import config` 및 Flask 기동 성공 (lazy 검증 확인)
- `python app.py` → GET `/` → 200 "newsmailing is running."
