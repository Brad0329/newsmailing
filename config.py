"""환경변수 로드 및 검증."""
import os

from dotenv import load_dotenv

from paths import app_dir

# .env 는 exe/소스 기준 디렉토리에서 로드 (PyInstaller 호환)
load_dotenv(app_dir() / ".env")


class ConfigError(Exception):
    pass


def _get(name: str, required: bool = True, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise ConfigError(f"환경변수 {name} 가 설정되지 않았습니다. .env 를 확인하세요.")
    return value


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


# Naver API
NAVER_CLIENT_ID = _get("NAVER_CLIENT_ID", required=False)
NAVER_CLIENT_SECRET = _get("NAVER_CLIENT_SECRET", required=False)

# SMTP
SMTP_HOST = _get("SMTP_HOST", required=False)
SMTP_PORT = _get_int("SMTP_PORT", 587)
SMTP_USER = _get("SMTP_USER", required=False)
SMTP_PASS = _get("SMTP_PASS", required=False)
SMTP_FROM = _get("SMTP_FROM", required=False)
SMTP_USE_TLS = _get_bool("SMTP_USE_TLS", True)

# Flask
FLASK_HOST = _get("FLASK_HOST", required=False, default="127.0.0.1")
FLASK_PORT = _get_int("FLASK_PORT", 5000)
FLASK_DEBUG = _get_bool("FLASK_DEBUG", True)


def check_naver() -> None:
    """Naver API 호출 전 검증."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise ConfigError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 설정되지 않았습니다.")


def check_smtp() -> None:
    """메일 발송 전 검증."""
    missing = [
        name
        for name, value in [
            ("SMTP_HOST", SMTP_HOST),
            ("SMTP_USER", SMTP_USER),
            ("SMTP_PASS", SMTP_PASS),
            ("SMTP_FROM", SMTP_FROM),
        ]
        if not value
    ]
    if missing:
        raise ConfigError(f"SMTP 설정 누락: {', '.join(missing)}")
