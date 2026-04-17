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
