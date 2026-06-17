"""CLI 진입점. 로컬 폴더/Git URL을 분석해 정형 Markdown 인수인계 문서를 출력하거나,
웹 화면 모드로 구동한다.

사용 예:
    python -m handover ./my-project
    python -m handover ./my-project -o handover.md
    python -m handover https://github.com/owner/repo.git
    python -m handover --serve            # 웹 화면 (기본 http://127.0.0.1:8765)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, export, snapshot, source
from .service import generate_document
from .template import render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="handover",
        description="프로젝트 폴더/Git URL에서 설치·실행·주의사항을 뽑아 정형 인수인계 문서를 생성합니다.",
    )
    parser.add_argument(
        "path", nargs="?",
        help="분석할 프로젝트 폴더 경로 또는 Git 저장소 URL (--serve 모드에서는 생략)",
    )
    parser.add_argument(
        "-o", "--output",
        help="결과를 저장할 파일 경로 (생략 시 표준 출력으로 보냄)",
    )
    parser.add_argument(
        "--snapshot", metavar="PATH",
        help="재분석 diff용 스냅샷(JSON) 경로. 파일이 있으면 이전 분석과 비교해 "
             "'변경 사항' 섹션을 추가하고, 실행 후 항상 최신 스냅샷으로 갱신한다.",
    )
    parser.add_argument("--gui", action="store_true",
                        help="네이티브 데스크톱 창(tkinter)으로 실행")
    parser.add_argument("--serve", action="store_true",
                        help="웹 화면 모드로 실행")
    parser.add_argument("--host", default="127.0.0.1",
                        help="웹 서버 바인드 호스트 (기본 127.0.0.1=로컬 전용)")
    parser.add_argument("--port", type=int, default=8765, help="웹 서버 포트 (기본 8765)")
    parser.add_argument("--no-browser", action="store_true",
                        help="웹 모드에서 브라우저 자동 열기를 끈다")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _force_utf8_io() -> None:
    """stdout/stderr를 UTF-8로 통일한다.

    한글 Windows 콘솔 기본 인코딩(cp949)은 문서의 em-dash·박스 문자를 인코딩하지 못해
    UnicodeEncodeError로 죽고, 진행 메시지도 깨진다. 출력 인코딩을 UTF-8로 고정해
    동작을 결정적으로 만든다 (Markdown 생성 도구의 출력은 UTF-8이 기본이어야 함).
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # Python 3.7+
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    """종료 코드를 반환한다 (0=성공, 2=입력 오류, 1=그 외 실패)."""
    _force_utf8_io()
    args = build_parser().parse_args(argv)

    # 데스크톱 GUI 모드.
    if args.gui:
        from .gui import run
        run()
        return 0

    # 웹 화면 모드: --serve를 줬거나, 인자 없이 실행(=exe 더블클릭)한 경우.
    # 후자에서는 브라우저를 자동으로 열어 클릭 한 번으로 바로 쓸 수 있게 한다.
    if args.serve or not args.path:
        from .web import serve  # http.server 의존을 이 경로에서만 로드
        launched_by_click = not args.path and not args.serve
        open_browser = launched_by_click and not args.no_browser
        try:
            serve(args.host, args.port, open_browser=open_browser)
        except OSError as exc:
            print(f"오류: 웹 서버를 시작할 수 없습니다 (포트 {args.port}가 사용 중일 수 있음) → {exc}",
                  file=sys.stderr)
            return 1
        return 0

    # 로컬 경로/URL을 해석·분석·렌더링 (URL이면 임시 클론 후 자동 정리).
    try:
        document, meta = generate_document(args.path)
    except source.SourceError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(f"오류: 읽기 권한이 없습니다 → {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"오류: 파일 시스템 접근 중 문제가 발생했습니다 → {exc}", file=sys.stderr)
        return 1

    # 재분석 diff: 이전 스냅샷이 있으면 변경 사항을 섹션으로 추가하고, 항상 최신으로 갱신.
    if args.snapshot:
        snap_path = Path(args.snapshot).expanduser()
        new_snap = snapshot.to_snapshot(meta)
        try:
            prev = snapshot.load(snap_path)
        except ValueError as exc:
            # 손상된 스냅샷이면 diff는 건너뛰고 새로 덮어쓴다 (작업을 막지 않음).
            print(f"경고: {exc} — diff를 건너뜁니다.", file=sys.stderr)
            prev = None
        if prev is not None:
            d = snapshot.diff(prev, new_snap)
            document = render_markdown(meta, diff_md=snapshot.render_diff_md(d))
        try:
            snapshot.save(snap_path, new_snap)
        except OSError as exc:
            print(f"경고: 스냅샷 저장 실패 → {exc}", file=sys.stderr)

    if args.output:
        out_path = Path(args.output).expanduser()
        # 확장자가 .html이면 HTML로 변환, 그 외(.md/.txt 등)는 Markdown 원문.
        content = export.render(document, out_path.suffix, f"{meta.name} 인수인계 문서")
        try:
            out_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            print(f"오류: 결과 파일을 저장하지 못했습니다 → {exc}", file=sys.stderr)
            return 1
        # 진행 상황은 stderr로 보내, stdout 리다이렉트 시 문서만 깨끗하게 남게 한다.
        print(f"완료: {out_path} 생성 ({len(meta.notes)}건 확인 필요)", file=sys.stderr)
    else:
        _print_utf8(document)

    return 0


def _print_utf8(text: str) -> None:
    """문서를 stdout으로 출력한다.

    한글 Windows 콘솔의 기본 인코딩(cp949)은 em-dash·박스 문자 등을 인코딩하지 못해
    UnicodeEncodeError로 죽는다. stdout을 UTF-8로 강제하고, 그래도 안 되는 콘솔에서는
    인코딩 불가 문자를 대체해 출력이 끊기지 않게 한다.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
        print(text)
    except (AttributeError, ValueError, UnicodeEncodeError):
        sys.stdout.buffer.write(text.encode("utf-8", errors="backslashreplace"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    raise SystemExit(main())
