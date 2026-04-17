"""exe 배포판 엔트리포인트.

- waitress 로 프로덕션 기동 (Flask dev reloader 비활성)
- 지정 포트가 이미 사용 중이면 다음 빈 포트로 자동 이동
- 1초 후 기본 브라우저로 http://127.0.0.1:{port}/ 자동 오픈
- Ctrl+C 로 종료
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser

from paths import app_dir


def _ensure_env_exists() -> None:
    env_path = app_dir() / ".env"
    if env_path.exists():
        return
    print("[!] .env 파일을 찾을 수 없습니다.", file=sys.stderr)
    print(f"    위치: {env_path}", file=sys.stderr)
    print("    .env.example 를 복사해 값을 채운 뒤 다시 실행하세요.", file=sys.stderr)
    print("")
    input("엔터 키를 누르면 종료합니다...")
    sys.exit(1)


def _find_free_port(preferred: int, max_tries: int = 20) -> int:
    port = preferred
    for _ in range(max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"포트 {preferred}~{preferred + max_tries - 1} 모두 사용 중")


def _open_browser_later(url: str, delay: float = 1.2) -> None:
    def _go():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_go, daemon=True).start()


def _make_stdout_tolerant() -> None:
    """Windows cp949 콘솔에서 em-dash 등 비 ASCII가 있어도 죽지 않도록."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> None:
    _make_stdout_tolerant()
    _ensure_env_exists()

    # config 는 .env 확인 후 import (ConfigError 방지)
    import config
    from app import app

    host = "127.0.0.1"
    port = _find_free_port(config.FLASK_PORT)
    url = f"http://{host}:{port}/"

    print("=" * 60)
    print(f"  newsmailing 기동: {url}")
    print("  브라우저가 자동으로 열립니다. 창을 닫으면 서버가 종료됩니다.")
    print("=" * 60)

    _open_browser_later(url)

    try:
        from waitress import serve

        serve(app, host=host, port=port, threads=4)
    except KeyboardInterrupt:
        print("\n종료합니다.")


if __name__ == "__main__":
    main()
