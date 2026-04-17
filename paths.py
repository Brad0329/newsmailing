"""경로 해석 — PyInstaller로 얼린 exe에서도 일관된 기준 디렉토리 제공.

- 일반 파이썬 실행: 소스 파일이 있는 프로젝트 루트
- PyInstaller --onefile exe 실행: exe 파일이 놓인 폴더 (임시 압축해제 경로 아님)
"""
from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """운영 디렉토리 — .env, data/ 등 사용자 데이터가 놓이는 곳."""
    if getattr(sys, "frozen", False):
        # PyInstaller exe
        return Path(sys.executable).resolve().parent
    # 일반 소스 실행
    return Path(__file__).resolve().parent
