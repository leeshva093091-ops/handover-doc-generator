"""PyInstaller 빌드용 GUI 진입 스크립트 (handover-gui.exe 엔트리포인트).

--windowed(콘솔 없음)로 빌드해 네이티브 Windows 프로그램처럼 동작한다.
"""

from handover.gui import run

if __name__ == "__main__":
    run()
