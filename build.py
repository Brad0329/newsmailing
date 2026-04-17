"""PyInstaller 빌드 스크립트.

생성물:
  dist/vanassomailing/
    ├── vanassomailing.exe
    ├── .env.example
    ├── manual.md
    └── data/  (빈 폴더, 런타임 생성물 저장)

사용법:
  pip install -r requirements.txt
  python build.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
ICON_PNG = ROOT / "data" / "vansso.png"
ICON_ICO = ROOT / "vansso.ico"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
BUNDLE = DIST / "vanassomailing"
EXE_NAME = "vanassomailing"


def make_ico():
    if not ICON_PNG.exists():
        print(f"[!] 아이콘 원본이 없습니다: {ICON_PNG}")
        sys.exit(1)
    print(f"[*] ico 변환: {ICON_PNG} -> {ICON_ICO}")
    img = Image.open(ICON_PNG).convert("RGBA")
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICON_ICO, sizes=sizes)


def clean():
    for p in (DIST, BUILD):
        if p.exists():
            shutil.rmtree(p)
    spec = ROOT / f"{EXE_NAME}.spec"
    if spec.exists():
        spec.unlink()


def run_pyinstaller():
    print("[*] PyInstaller 실행")
    # --add-data 포맷: SRC;DEST (Windows)
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--name", EXE_NAME,
        "--icon", str(ICON_ICO),
        "--add-data", f"templates{';'}templates",
        "--add-data", f"static{';'}static",
        "--collect-submodules", "waitress",
        "run.py",
    ]
    subprocess.run(args, check=True)


def assemble_bundle():
    print(f"[*] 배포 번들 구성: {BUNDLE}")
    BUNDLE.mkdir(parents=True, exist_ok=True)

    # exe
    src_exe = DIST / f"{EXE_NAME}.exe"
    shutil.copy2(src_exe, BUNDLE / f"{EXE_NAME}.exe")
    src_exe.unlink()  # dist 루트의 exe는 제거 (번들에 통합됨)

    # 함께 배포할 파일들
    for name in (".env.example", "manual.md"):
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, BUNDLE / name)

    # 빈 data 폴더 (런타임 settings.json/history.json 생성 위치)
    (BUNDLE / "data").mkdir(exist_ok=True)

    # 아이콘 ico 는 빌드 부산물 - 제거
    if ICON_ICO.exists():
        ICON_ICO.unlink()

    # build/ 와 spec 정리
    if BUILD.exists():
        shutil.rmtree(BUILD)
    spec = ROOT / f"{EXE_NAME}.spec"
    if spec.exists():
        spec.unlink()


def main():
    make_ico()
    clean()
    try:
        run_pyinstaller()
    except subprocess.CalledProcessError as e:
        print(f"[!] PyInstaller 실패: rc={e.returncode}")
        sys.exit(e.returncode)
    assemble_bundle()
    print(f"[OK] 빌드 완료: {BUNDLE}")


if __name__ == "__main__":
    main()
