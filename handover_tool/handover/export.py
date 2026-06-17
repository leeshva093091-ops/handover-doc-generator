"""인수인계 문서(Markdown)를 다른 포맷으로 내보내기 (3단계 포맷 확장).

표준 라이브러리만 사용한다. 이 도구가 생성하는 문서가 쓰는 한정된 Markdown 문법
(제목 #/##/###, 불릿 -, 코드펜스 ```, 표 |...|, 인용 >, 인라인 `code`/**bold**)만
다루는 경량 변환기다. 범용 Markdown 파서가 아니다.
"""

from __future__ import annotations

import html
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")

_HTML_TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
 body {{ font-family: -apple-system, "Segoe UI", sans-serif; max-width: 860px;
         margin: 32px auto; padding: 0 16px; color: #1b1b1b; line-height: 1.6; }}
 h1 {{ color: #2d6cdf; border-bottom: 2px solid #eee; padding-bottom: 6px; }}
 h2 {{ margin-top: 28px; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
 code {{ background: #f1f3f5; padding: 1px 5px; border-radius: 4px;
         font-family: Consolas, monospace; }}
 pre {{ background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }}
 pre code {{ background: none; padding: 0; }}
 blockquote {{ color: #666; border-left: 4px solid #ddd; margin: 8px 0; padding: 4px 12px; }}
 table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
 th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
 th {{ background: #f6f8fa; }}
</style></head>
<body>
{body}
</body></html>
"""


def to_text(markdown: str) -> str:
    """Markdown은 이미 평문이므로 그대로 반환한다."""
    return markdown


def _inline(text: str) -> str:
    """인라인 서식(**bold**, `code`)을 HTML로. 먼저 이스케이프 후 치환한다."""
    escaped = html.escape(text)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _CODE.sub(r"<code>\1</code>", escaped)
    return escaped


def _table_html(rows: list[str]) -> str:
    """`|`로 둘러싼 표 블록을 HTML 표로 변환한다 (구분선 행은 제외)."""
    parsed = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    if not parsed:
        return ""
    header = parsed[0]
    body_rows = [
        r for r in parsed[1:]
        if not all(set(c) <= set("-: ") for c in r)  # |---|---| 구분선 제거
    ]
    th = "".join(f"<th>{_inline(c)}</th>" for c in header)
    trs = "".join(
        "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
        for r in body_rows
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def to_html(markdown: str, title: str = "인수인계 문서") -> str:
    """경량 Markdown → HTML 변환."""
    lines = markdown.splitlines()
    body: list[str] = []
    i, n = 0, len(lines)
    in_code = False
    code_buf: list[str] = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if not in_code:
                in_code, code_buf = True, []
            else:
                in_code = False
                body.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # 표 블록 (연속된 | 줄)
        if stripped.startswith("|"):
            tbl = []
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            body.append(_table_html(tbl))
            continue

        # 불릿 목록 (연속된 - 줄)
        if stripped.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            body.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
            continue

        if stripped.startswith("### "):
            body.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            body.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            body.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped.startswith("> "):
            body.append(f"<blockquote>{_inline(stripped[2:])}</blockquote>")
        elif stripped:
            body.append(f"<p>{_inline(stripped)}</p>")
        i += 1

    # 닫히지 않은 코드펜스 방어
    if in_code and code_buf:
        body.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")

    return _HTML_TEMPLATE.format(title=html.escape(title), body="\n".join(body))


def render(markdown: str, ext: str, title: str = "인수인계 문서") -> str:
    """확장자(.md/.txt/.html 등)에 맞는 내용 문자열을 반환한다."""
    if ext.lower() in (".html", ".htm"):
        return to_html(markdown, title)
    # .md, .markdown, .txt, 그 외 → 원문(Markdown 평문) 그대로
    return markdown
