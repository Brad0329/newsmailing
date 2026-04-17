# vanassomailing 사용 매뉴얼

## 프로그램 개요

`(사)한국지불결제밴협회` 내부 뉴스 메일링 자동화 도구.
- 관심 키워드를 입력해 Naver 뉴스에서 어제/오늘 기사를 한 번에 수집
- 담당자가 체크박스로 기사를 선별
- 실 발송 전 미리보기에서 본문을 직접 편집 가능
- 저장된 수신자 리스트에 HTML 메일로 일괄 발송

---

## 설치 방법 두 가지

**A. exe 배포판** — 일반 사용자. Python 설치 불필요. 배포 폴더 복사만.
**B. 소스 클론** — 개발/유지보수 담당자. Git+Python 필요. 수정·재빌드 가능.

둘 중 상황에 맞는 섹션을 따라가세요.

---

## A. 설치 (exe 배포판, 실행용 PC)

배포 폴더 `vanassomailing/` 을 적당한 위치에 복사합니다. 예: `C:\Tools\vanassomailing\`

폴더 구성:
```
vanassomailing\
├── vanassomailing.exe        실행 파일
├── .env.example              설정 템플릿
├── .env                      실제 설정 (사용자가 작성 - 아래 참조)
├── data\                     자동 생성. 수신자 리스트 등 저장
├── manual.md                 본 매뉴얼
└── README.txt                간단 안내
```

### `.env` 파일 작성 (최초 1회)

`.env.example`을 복사해 `.env`를 만들고 아래 값을 채웁니다.

```ini
# Naver 검색 API
NAVER_CLIENT_ID=xxxxxxxxxxxxxxxx
NAVER_CLIENT_SECRET=xxxxxxxxxx

# 회사 메일 SMTP (hiworks 기준)
SMTP_HOST=smtps.hiworks.com
SMTP_PORT=465
SMTP_USER=admin@vanasso.kr
SMTP_PASS=비밀번호
SMTP_FROM=admin@vanasso.kr
SMTP_USE_TLS=false          # 포트 465=false (SSL 직접), 포트 587=true (STARTTLS)

# Flask
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=false
```

**중요**:
- `.env`는 시크릿이 들어있으므로 절대 외부 공유 금지
- **포트와 TLS 매핑**이 맞아야 발송됨 (자주 틀리는 부분)
  - `465` → `SMTP_USE_TLS=false` (SSL 직접)
  - `587` → `SMTP_USE_TLS=true` (STARTTLS)

### Naver 검색 API 키 발급

1. https://developers.naver.com/apps 접속
2. 애플리케이션 등록 → 이름: `vanassomailing`
3. 사용 API: **검색** 체크
4. 환경 → WEB: 웹 서비스 URL에 `http://localhost:5000` 입력
5. Client ID / Secret 발급 → `.env`에 기입

---

## B. 설치 (Git 클론, 개발자/유지보수용)

소스에서 직접 실행하거나 수정·재빌드할 때 사용합니다.

### 사전 요구사항

- **Git** for Windows — https://git-scm.com/download/win
- **Python 3.11+** — https://www.python.org/downloads/
  - 설치 시 "Add Python to PATH" 체크 필수
- **GitHub 접근 권한** — 리포지토리가 private인 경우 SSH 키 또는 Personal Access Token 필요

### 클론 및 실행

PowerShell 또는 명령 프롬프트에서:

```bash
# 1. 원하는 위치로 이동 (예: Documents)
cd %USERPROFILE%\Documents

# 2. 리포지토리 클론
git clone https://github.com/Brad0329/newsmailing.git
cd newsmailing

# 3. (권장) 가상환경 생성·활성화
python -m venv venv
venv\Scripts\activate

# 4. 의존성 설치
pip install -r requirements.txt

# 5. .env 작성 (템플릿 복사 후 편집)
copy .env.example .env
notepad .env        # 실제 Naver 키 / SMTP 정보 입력 후 저장

# 6. 실행
python app.py
```

정상 기동하면 콘솔에 `Running on http://127.0.0.1:5000` 메시지가 뜹니다. 브라우저로 접속해 사용.

### `.env` 작성은 A 섹션 참조

위 A 섹션의 "[.env 파일 작성]" 항목과 동일합니다. 포트/TLS 매핑 주의.

### Naver API 키도 A 섹션 참조

개발자라도 API 키는 별도 발급 필요 (계정별 호출 한도 공유됨).

### 업데이트 (새 커밋 반영)

```bash
cd newsmailing
git pull
pip install -r requirements.txt     # requirements.txt 변경 시
```

`.env` 와 `data\settings.json` 은 로컬에 그대로 유지 (gitignore에 등록됨).

### exe 빌드 (배포판 만들기)

클론받은 소스에서 PyInstaller로 `vanassomailing.exe` 빌드. **현재 빌드 스크립트는 포함되지 않음** — 빌드 진행 시 별도 문서화 예정. 준비물:
- `data\vansso.png` → `.ico` 변환 (예: https://convertio.co/png-ico/)
- `pyinstaller` 및 `waitress` 설치 (`pip install pyinstaller waitress`)
- 엔트리포인트 스크립트(`run.py`) 작성 — 브라우저 자동 오픈, waitress 기동

### 종료

콘솔 창에서 `Ctrl+C` 또는 창 닫기.

### 가상환경 비활성화

```bash
deactivate
```

---

## 실행 (exe 배포판)

Git 클론 사용자는 B 섹션의 실행 단계를 참조하세요.

### 시작

1. `vanassomailing.exe` 더블클릭
2. 검은 콘솔 창이 뜸 (서버 기동 메시지 출력)
3. 잠시 후 기본 브라우저에서 `http://localhost:5000` 자동 오픈
4. 브라우저에 "newsmailing" 화면 표시

### 종료

콘솔 창을 닫거나 `Ctrl+C`.

### 주의

- **콘솔 창을 닫으면 서버도 종료**됨. 작업 중에는 열어두기.
- 포트 `5000`이 이미 사용 중이면 에러. 다른 프로그램 종료 후 재실행.

---

## 사용법

### 화면 구성

```
┌─ 검색어 카드 ─────────────────────────────┐
│ 검색어: [카드 보안, 핀테크, 해킹, ...]      │
│ 키워드당 기사 수: [5]  [기사 찾기]         │
└───────────────────────────────────────────┘

┌─ 결과 카드 (검색 후 표시) ────────────────┐
│ ☑ 제목1 / 출처1 / 시각 / 검색어          │
│ ☐ 제목2 / 출처2 / 시각 / 검색어          │
│ [전체 선택] [전체 해제]                   │
└───────────────────────────────────────────┘

┌─ 메일 발송 카드 (항상 표시) ──────────────┐
│ 보내는 사람 이름: [(사)한국지불결제밴협회]│
│ 수신자: [alice@x.com; bob@x.com; ...]     │
│ 제목: [[VAN협회] 금일 업계 동향 기사]     │
│ 본문 서두: [안녕하세요. ...]               │
│ 본문 말미(서명): [행복한 하루 되세요...]  │
│ [메일 보내기]                              │
└───────────────────────────────────────────┘
```

### 일일 작업 흐름

1. **검색어 입력** (쉼표 `,` 구분)
   - 예: `카드 보안, 핀테크, 해킹, 전자결제, 카드사 제재`
   - 약 20개 정도까지 권장
2. **키워드당 기사 수** (기본 5): 각 검색어에서 뽑을 최대 기사 수
3. **[기사 찾기]** 클릭 → 어제~오늘 기사가 키워드 순, 최신순으로 표시
4. **체크박스로 발송할 기사 선택** (필요 시 [전체 선택])
5. **메일 발송 카드 확인**: 수신자는 지난 발송 목록이 자동으로 채워짐. 추가하려면 끝에 `; 새주소@회사.com` 이어서 입력.
6. **[메일 보내기]** 클릭 → 미리보기 팝업
7. **미리보기 팝업**에서:
   - 발신자/수신자/제목이 상단에 표시
   - 본문 영역(점선 테두리)을 **마우스로 클릭하면 직접 편집 가능**
     - `Ctrl+B` 굵게, `Ctrl+I` 기울임, `Ctrl+U` 밑줄, `Ctrl+Z` 되돌리기
     - 기사 삭제/문장 수정/문구 추가 자유
   - **[확인 (발송)]** 클릭 → 실제 발송
   - **[취소]** 클릭 → 발송 취소, 편집 내용 폐기

### 수신자 리스트 관리

- **자동 저장**: 메일 발송 성공 시 현재 입력된 수신자 리스트가 `data\settings.json`에 저장됨
- **자동 로드**: 다음 실행 시 저장된 리스트가 자동으로 입력됨
- **추가**: textarea 끝에 `;` 찍고 새 주소 입력
- **삭제**: 해당 주소를 직접 지움
- **주소 구분자**: 세미콜론 `;` (쉼표 `,` 아님 — 주의)

### 디폴트 값 변경

UI에 자동으로 채워지는 제목/서두/서명 디폴트는 **코드 내 상수**(`defaults.py`)에서 정의됩니다. 변경하려면:
1. 임시 변경(이번만): 화면에서 수정 후 발송 — 저장되지 않음
2. 영구 변경: 개발자에게 `defaults.py` 수정 요청 (차기 빌드 필요)

---

## 트러블슈팅

### "NAVER_CLIENT_ID 가 설정되지 않았습니다" 에러
`.env` 파일이 없거나 키가 누락됨. 위 "[.env 파일 작성]" 참조.

### "발송 실패: Connection unexpectedly closed" 에러
SMTP 포트와 TLS 설정 불일치. `.env`에서:
- 포트 465 → `SMTP_USE_TLS=false`
- 포트 587 → `SMTP_USE_TLS=true`

### "발송 실패: 535 Authentication" 에러
SMTP 비밀번호 오류 또는 외부 앱 접속 차단. hiworks 계정 확인.

### 메일이 상대방 스팸함으로 감
자사 도메인(`vanasso.kr`) DNS에 SPF/DKIM/DMARC 미설정이 주 원인.
- 도메인 관리자에게 다음 레코드 요청:
  - SPF: `v=spf1 include:_spf.hiworks.com ~all`
  - DKIM: hiworks 관리 콘솔에서 활성화 후 발급되는 공개키 레코드
  - DMARC: `v=DMARC1; p=none; rua=mailto:admin@vanasso.kr`

### 실행 시 Windows Defender/백신 경고
PyInstaller로 만든 exe의 흔한 오탐. 회사 IT팀에 화이트리스트 등록 요청, 또는 "자세히 → 실행" 허용.

### 포트 5000 이미 사용 중
다른 프로그램이 점유 중. 해당 프로그램 종료 후 재실행. 영구 변경하려면 `.env`에서 `FLASK_PORT` 조정.

### 기사가 "어제/오늘" 필터에 너무 적게 잡힘
키워드가 너무 좁거나 해당 기간에 보도가 적은 경우. 관련 검색어를 추가하거나 "키워드당 기사 수"를 늘려 후보 풀 확장.

---

## 운영 체크리스트

### 매일 발송 전
- [ ] `.env` 파일 손상/누락 확인 (간혹 실수로 덮어씀)
- [ ] 인터넷 연결 확인 (Naver API + SMTP 둘 다 외부 호출)
- [ ] Naver API 일일 한도 25,000회 — 일반 사용으로는 여유

### 주기적 확인
- [ ] `data\settings.json` 수신자 리스트 최신성 — 퇴사자/주소 변경자
- [ ] 발송 후 `admin@vanasso.kr` 수신함에 바운스(반송) 메일 확인

### 백업
- [ ] `.env` (별도 안전 보관)
- [ ] `data\settings.json` (수신자 복원용)

---

## 기술 정보 (개발자/IT팀 참고)

- **언어/프레임워크**: Python 3.11 + Flask + waitress (프로덕션 WSGI)
- **UI**: 서버 사이드 템플릿 + Vanilla JS (외부 CDN 의존 없음, 오프라인 가능)
- **외부 의존**: Naver 검색 API, 회사 SMTP 서버
- **로컬 네트워크**: 127.0.0.1만 바인딩 — 타 PC에서 접속 불가 (보안)
- **데이터 저장**: 파일 기반 `data\settings.json` (JSON). DB 없음.
- **프로세스 구조**: 단일 프로세스 단일 스레드(waitress 기본). 동시 사용자 1명 상정.

재배포/업데이트가 필요한 변경:
- `defaults.py` (디폴트 제목/서두/서명)
- 언론사 도메인 매핑(`naver_client.py`의 `DOMAIN_TO_SOURCE`)
- 버그 수정/기능 추가
