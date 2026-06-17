"""표준 라이브러리만으로 동작하는 간단한 웹 화면 (2-2).

외부 패키지 없이 http.server로 구동한다(폐쇄망 의존성 0 유지). 로컬 폴더 경로나 Git URL을
입력받아 인수인계 문서를 생성·표시하고, 브라우저에서 Markdown으로 내려받게 한다.

보안: 이 서버는 입력한 로컬 경로의 파일을 읽고 임의 Git URL을 클론할 수 있다. 그래서
기본 바인드를 127.0.0.1(로컬호스트)로 두어 외부 노출을 막는다. 외부 공개는 권장하지 않는다.
"""

from __future__ import annotations

import html
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import source
from .models import ProjectMetadata
from .service import generate_document

_STYLE = """
  body { font-family: -apple-system, "Segoe UI", sans-serif; max-width: 860px;
         margin: 24px auto; padding: 0 16px; color: #1b1b1b; }
  h1 { font-size: 1.4rem; }
  input[type=text] { width: 100%; padding: 10px; font-size: 1rem; box-sizing: border-box; }
  button { margin-top: 10px; padding: 10px 18px; font-size: 1rem; cursor: pointer; }
  .error { color: #b00020; background: #fdecea; padding: 10px 12px; border-radius: 6px; }
  .summary { background: #eef4ff; padding: 10px 12px; border-radius: 6px; }
  .warn { background: #fff4e5; padding: 10px 12px; border-radius: 6px; }
  textarea { width: 100%; height: 420px; font-family: Consolas, monospace; font-size: .85rem;
             box-sizing: border-box; }
  a.btn { display: inline-block; margin-top: 8px; }
"""


def _page(body: str) -> str:
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>인수인계 문서 생성기</title><style>{_STYLE}</style></head>"
            f"<body>{body}</body></html>")


def render_form(error: str | None = None, value: str = "") -> str:
    """입력 폼 페이지."""
    error_html = f"<p class='error'>⚠️ {html.escape(error)}</p>" if error else ""
    return _page(
        "<h1>📄 인수인계 문서 생성기</h1>"
        "<p>프로젝트 폴더 경로나 Git 저장소 URL을 입력하면 정형 인수인계 문서를 만들어 줍니다.</p>"
        "<form method='post' action='/analyze'>"
        "<label for='source'>폴더 경로 또는 Git URL</label><br>"
        f"<input type='text' id='source' name='source' value='{html.escape(value)}' "
        "placeholder='예: ./samples/demo_project  또는  https://github.com/owner/repo.git' autofocus>"
        "<br><button type='submit'>분석하기</button>"
        "</form>"
        f"{error_html}"
    )


def render_result(src: str, document: str, meta: ProjectMetadata) -> str:
    """분석 결과 페이지 (요약 + 문서 + 다운로드)."""
    # 민감정보가 있으면 눈에 띄게 경고.
    if meta.sensitive:
        summary = (f"<p class='warn'>⚠️ 민감정보 의심 {len(meta.sensitive)}건 발견 — "
                   "문서 공유 전 반드시 확인하세요.</p>")
    else:
        summary = "<p class='summary'>민감정보 의심 항목은 발견되지 않았습니다 (직접 검토 권장).</p>"

    # 데이터 URI로 서버 왕복 없이 즉시 다운로드. quote로 안전하게 인코딩.
    href = "data:text/markdown;charset=utf-8," + urllib.parse.quote(document)
    filename = f"{meta.name}-handover.md"

    return _page(
        f"<h1>📄 {html.escape(meta.name)}</h1>"
        f"<p><b>출처:</b> {html.escape(meta.root)}</p>"
        f"{summary}"
        f"<a class='btn' download='{html.escape(filename)}' href='{href}'>⬇ Markdown 다운로드</a>"
        "<h2>미리보기</h2>"
        f"<textarea readonly>{html.escape(document)}</textarea>"
        "<p><a href='/'>← 다른 프로젝트 분석</a></p>"
    )


class _Handler(BaseHTTPRequestHandler):
    def _send_html(self, status: int, content: str) -> None:
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler 규약)
        if self.path.startswith("/favicon"):
            self.send_response(204)
            self.end_headers()
            return
        self._send_html(200, render_form())

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/analyze"):
            self._send_html(404, _page("<p>알 수 없는 경로입니다.</p>"))
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        params = urllib.parse.parse_qs(body)
        src = (params.get("source", [""])[0] or "").strip()

        if not src:
            self._send_html(400, render_form(error="경로 또는 URL을 입력하세요."))
            return
        try:
            document, meta = generate_document(src)
        except source.SourceError as exc:
            self._send_html(200, render_form(error=str(exc), value=src))
            return
        except (PermissionError, OSError) as exc:
            self._send_html(200, render_form(error=f"분석 중 오류: {exc}", value=src))
            return
        self._send_html(200, render_result(src, document, meta))

    def log_message(self, *args) -> None:  # noqa: D401
        """기본 접근 로그를 끄고 콘솔을 조용히 유지한다."""
        return


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    """웹 서버를 구동한다 (Ctrl+C로 종료).

    open_browser=True면 기본 브라우저로 화면을 자동으로 연다 (exe 더블클릭 시 사용).
    """
    httpd = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"
    print(f"인수인계 도구 웹 서버 실행 중 → {url}")
    print("브라우저에서 위 주소로 접속하세요. (이 창을 닫거나 Ctrl+C를 누르면 종료됩니다.)")
    if host not in ("127.0.0.1", "localhost"):
        print("주의: 로컬호스트 외부에 바인드되었습니다. 이 서버는 로컬 파일 접근/저장소 클론이 "
              "가능하므로 신뢰된 망에서만 사용하세요.")
    if open_browser:
        # 소켓은 이미 listen 상태이므로, 브라우저 요청은 serve_forever가 받아 처리한다.
        try:
            webbrowser.open(url)
        except OSError:
            pass  # 브라우저 자동 열기는 부가 기능 — 실패해도 서버는 계속 돈다.
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        httpd.server_close()
