"""간단한 파일 기반 설정 저장소 — 수신자 리스트 지속화."""
from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_SETTINGS_FILE = _DATA_DIR / "settings.json"


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
