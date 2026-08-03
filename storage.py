"""간단한 파일 기반 설정 저장소 — 수신자 리스트 / 발송 내역 / 예약 발송 지속화."""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paths import app_dir

_DATA_DIR = app_dir() / "data"
_SETTINGS_FILE = _DATA_DIR / "settings.json"
_HISTORY_FILE = _DATA_DIR / "history.json"
_DOMAIN_MAP_FILE = _DATA_DIR / "domain_map.json"
_SCHEDULED_DIR = _DATA_DIR / "scheduled"

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


# ---------- 도메인 → 언론사 매핑 ----------


def load_domain_map() -> dict[str, str]:
    """data/domain_map.json 로드. 없거나 깨지면 빈 dict — 도메인 문자열로 폴백."""
    if not _DOMAIN_MAP_FILE.exists():
        return {}
    try:
        data = json.loads(_DOMAIN_MAP_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # 방어적 정규화: key는 소문자, value는 문자열
        return {
            str(k).strip().lower(): str(v).strip()
            for k, v in data.items()
            if str(k).strip() and str(v).strip()
        }
    except (json.JSONDecodeError, OSError):
        return {}


# ---------- 예약 발송 ----------
#
# 구조:
#   data/scheduled/<id>/meta.json        (메일 정보 + scheduled_at + status)
#   data/scheduled/<id>/attachments/*    (첨부 원본 파일)
#
# status: pending → done (성공 후 폴더 삭제) / failed / missed


def _scheduled_dir(schedule_id: str) -> Path:
    return _SCHEDULED_DIR / schedule_id


def _meta_path(schedule_id: str) -> Path:
    return _scheduled_dir(schedule_id) / "meta.json"


def _attachments_dir(schedule_id: str) -> Path:
    return _scheduled_dir(schedule_id) / "attachments"


def create_scheduled(
    meta: dict,
    attachments: list[tuple[str, bytes, str | None]] | None = None,
) -> str:
    """새 예약 생성. meta는 recipients/subject/intro/signature/sender_*/html_fragment/articles/scheduled_at 포함.

    반환: 새 schedule_id (uuid4 hex).
    """
    schedule_id = uuid.uuid4().hex
    folder = _scheduled_dir(schedule_id)
    folder.mkdir(parents=True, exist_ok=True)

    full_meta = dict(meta)
    full_meta["schedule_id"] = schedule_id
    full_meta.setdefault("created_at", datetime.now(_KST).isoformat(timespec="seconds"))
    full_meta.setdefault("status", "pending")

    # 첨부파일 저장 + 메타에 파일명/크기 기록
    attach_list: list[dict] = []
    if attachments:
        att_dir = _attachments_dir(schedule_id)
        att_dir.mkdir(parents=True, exist_ok=True)
        for idx, (filename, data, mimetype) in enumerate(attachments):
            if not filename or not data:
                continue
            # 디스크 저장 파일명은 순번 prefix로 충돌 회피
            safe_name = f"{idx:02d}_{_sanitize_filename(filename)}"
            (att_dir / safe_name).write_bytes(data)
            attach_list.append(
                {
                    "filename": filename,
                    "disk_name": safe_name,
                    "size": len(data),
                    "mimetype": mimetype or "",
                }
            )
    full_meta["attachments"] = attach_list

    _meta_path(schedule_id).write_text(
        json.dumps(full_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return schedule_id


def _sanitize_filename(name: str) -> str:
    # Windows 금지문자 / 경로 구분 제거
    bad = '<>:"/\\|?*\0'
    return "".join(c for c in name if c not in bad).strip() or "attachment"


def load_scheduled(schedule_id: str) -> dict | None:
    """메타 로드. 없으면 None. 첨부파일 바이너리는 포함하지 않음 (load_scheduled_attachments 별도)."""
    path = _meta_path(schedule_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_scheduled_attachments(
    schedule_id: str,
) -> list[tuple[str, bytes, str | None]]:
    """첨부파일 바이너리 로드. (filename, data, mimetype) 튜플 리스트."""
    meta = load_scheduled(schedule_id)
    if not meta:
        return []
    att_dir = _attachments_dir(schedule_id)
    result: list[tuple[str, bytes, str | None]] = []
    for entry in meta.get("attachments") or []:
        disk_name = entry.get("disk_name")
        filename = entry.get("filename") or disk_name
        mimetype = entry.get("mimetype") or None
        if not disk_name:
            continue
        path = att_dir / disk_name
        if not path.exists():
            continue
        result.append((filename, path.read_bytes(), mimetype))
    return result


def list_scheduled() -> list[dict]:
    """모든 예약 메타 목록. scheduled_at 오름차순 (가까운 순)."""
    if not _SCHEDULED_DIR.exists():
        return []
    result: list[dict] = []
    for sub in _SCHEDULED_DIR.iterdir():
        if not sub.is_dir():
            continue
        meta = load_scheduled(sub.name)
        if meta:
            result.append(meta)
    result.sort(key=lambda m: m.get("scheduled_at", ""))
    return result


def update_scheduled_status(schedule_id: str, status: str, **extra) -> None:
    meta = load_scheduled(schedule_id)
    if not meta:
        return
    meta["status"] = status
    meta.update(extra)
    _meta_path(schedule_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def delete_scheduled(schedule_id: str) -> bool:
    """예약 폴더 전체 삭제. 성공 여부 반환."""
    folder = _scheduled_dir(schedule_id)
    if not folder.exists():
        return False
    shutil.rmtree(folder, ignore_errors=True)
    return not folder.exists()
