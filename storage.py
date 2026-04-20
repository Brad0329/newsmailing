"""간단한 파일 기반 설정 저장소 — 수신자 리스트 / 발송 내역 지속화."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from paths import app_dir

_DATA_DIR = app_dir() / "data"
_SETTINGS_FILE = _DATA_DIR / "settings.json"
_HISTORY_FILE = _DATA_DIR / "history.json"

_KST = timezone(timedelta(hours=9))


def _load() -> dict:
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_recipients() -> str:
    """저장된 수신자 문자열 반환 (없으면 빈 문자열)."""
    return _load().get("recipients", "")


def save_recipients(recipients: str) -> None:
    data = _load()
    data["recipients"] = recipients or ""
    _save(data)


def load_keywords() -> str:
    return _load().get("keywords", "")


def save_keywords(keywords: str) -> None:
    data = _load()
    data["keywords"] = keywords or ""
    _save(data)


# 발송 시 저장되는 메일 카드 필드들. 없으면 defaults 쪽에서 폴백.
_MAIL_FIELDS = ("sender_name", "sender_email", "subject", "intro", "signature")


def load_mail_fields() -> dict:
    data = _load()
    return {k: data.get(k, "") for k in _MAIL_FIELDS}


def save_mail_fields(fields: dict) -> None:
    data = _load()
    for k in _MAIL_FIELDS:
        if k in fields:
            data[k] = fields.get(k) or ""
    _save(data)


# ---------- 저장된 메일 리스트 (여러 개, 이름 붙여서) ----------


def load_mailing_lists() -> list[dict]:
    """[{name, recipients}, ...] 이름 오름차순."""
    data = _load()
    lists = data.get("mailing_lists") or []
    if not isinstance(lists, list):
        return []
    # 구조 방어
    cleaned = []
    for item in lists:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        recipients = str(item.get("recipients") or "")
        if name:
            cleaned.append({"name": name, "recipients": recipients})
    cleaned.sort(key=lambda e: e["name"])
    return cleaned


def save_mailing_list(name: str, recipients: str) -> None:
    """같은 이름 있으면 덮어쓰기, 없으면 추가."""
    name = (name or "").strip()
    if not name:
        raise ValueError("리스트 이름이 비어 있습니다.")
    data = _load()
    lists = data.get("mailing_lists") or []
    if not isinstance(lists, list):
        lists = []
    found = False
    for item in lists:
        if isinstance(item, dict) and str(item.get("name") or "").strip() == name:
            item["recipients"] = recipients or ""
            found = True
            break
    if not found:
        lists.append({"name": name, "recipients": recipients or ""})
    data["mailing_lists"] = lists
    _save(data)


def delete_mailing_list(name: str) -> bool:
    """삭제 성공 여부 반환."""
    name = (name or "").strip()
    if not name:
        return False
    data = _load()
    lists = data.get("mailing_lists") or []
    if not isinstance(lists, list):
        return False
    new_lists = [
        item for item in lists
        if not (isinstance(item, dict) and str(item.get("name") or "").strip() == name)
    ]
    if len(new_lists) == len(lists):
        return False
    data["mailing_lists"] = new_lists
    _save(data)
    return True


# ---------- 발송 내역 ----------


def _load_history() -> list[dict]:
    if not _HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(data: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_history(subject: str, recipients_count: int, sent_count: int) -> None:
    """발송 1건을 기록. KST 기준 ISO 8601 포맷으로 저장."""
    entry = {
        "sent_at": datetime.now(_KST).isoformat(timespec="seconds"),
        "subject": subject or "",
        "recipients_count": int(recipients_count),
        "sent_count": int(sent_count),
    }
    history = _load_history()
    history.append(entry)
    _save_history(history)


def load_history() -> list[dict]:
    """저장된 발송 내역. 최신 발송이 앞에 오도록 반환."""
    history = _load_history()
    return sorted(history, key=lambda e: e.get("sent_at", ""), reverse=True)
