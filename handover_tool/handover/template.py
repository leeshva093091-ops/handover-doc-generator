"""메타데이터를 정형 분석 문서(Markdown)로 렌더링한다.

기준: 프로젝트를 모르는 사람이 '문서만 보고 이해 → 준비 → 실행'할 수 있을 것.
각 항목은 ✅ 자동 추출 / ✍ 직접 입력 필요 / ➖ 해당 없음 으로 상태를 구분해 표시한다.
"""

from __future__ import annotations

import datetime

from .models import ProjectMetadata

# 직접 작성이 필요한 빈 항목 표식 (GUI가 'N곳' 집계 시 본문의 '직접 작성 필요'만 센다).
_TODO = "✍ **직접 작성 필요**"
_NA = "➖ 해당 없음"
_PLACEHOLDER = _TODO  # 하위 호환


def _todo(hint: str) -> str:
    return f"{_TODO} — {hint}"


def _today(generated_on: str | None) -> str:
    return generated_on or datetime.date.today().isoformat()


def _assemble(name: str, generated_on: str | None, body: list[str]) -> str:
    """제목(분석대상명) + 작성일 + 표기 범례를 본문 앞에 붙여 완성한다."""
    todo_n = sum(line.count("직접 작성 필요") for line in body)
    header = [
        f"# {name}",
        "",
        f"_자동 생성 분석 문서 · 작성일 {_today(generated_on)}_",
        f"> 표기: ✅ 자동 추출 · ✍ 직접 입력 필요({todo_n}곳) · ➖ 해당 없음",
        "",
    ]
    return "\n".join(header + body)


def render_markdown(meta: ProjectMetadata, diff_md: str | None = None,
                    generated_on: str | None = None) -> str:
    """정형 분석 문서를 생성한다. 단일 파일과 프로젝트는 양식이 다르다."""
    if meta.kind == "file":
        return _render_file_markdown(meta, diff_md, generated_on)
    return _render_project_markdown(meta, diff_md, generated_on)


def _sensitive_table(meta) -> list[str]:
    lines = ["| 종류 | 위치 | 미리보기(마스킹) | 신뢰도 |", "|---|---|---|---|"]
    for f in meta.sensitive:
        lines.append(f"| {f.kind} | `{f.file}:{f.line}` | `{f.masked}` | {f.confidence} |")
    return lines


def _render_project_markdown(meta, diff_md=None, generated_on=None) -> str:
    """프로젝트(폴더/Git)용 — 이해→준비→실행 흐름으로 구성."""
    b: list[str] = []

    # 1. 개요
    b.append("## 1. 개요")
    b.append(f"- **이름**: {meta.name}")
    b.append(f"- **출처**: `{meta.root}`")
    b.append(f"- **주요 언어**: {', '.join(meta.languages) if meta.languages else _todo('주요 언어/기술 스택을 적으세요')}")
    if meta.readme_excerpt:
        b.append("- **목적/설명**:")
        b.append("")
        b.append("```")
        b.append(meta.readme_excerpt)
        b.append("```")
    else:
        b.append(f"- **목적/설명**: {_todo('이 프로젝트가 무엇을 하는지 1~2줄로 적으세요')}")
    b.append("")

    # 2. 실행 준비
    b.append("## 2. 실행 준비")
    b.append("### 준비사항(Prerequisites)")
    if meta.prerequisites:
        b.extend(f"- {p}" for p in meta.prerequisites)
    else:
        b.append(f"- {_todo('필요한 런타임/사전 설치 항목을 적으세요')}")
    b.append("")
    b.append("### 의존성")
    if meta.dependencies:
        for g in meta.dependencies:
            b.append(f"- **{g.source}**")
            b.extend(f"  - {item}" for item in g.items)
    else:
        b.append(f"- {_NA} (알려진 의존성 파일 없음 — 사용한다면 직접 추가)")
    b.append("")

    # 3. 환경 설정
    b.append("## 3. 환경 설정")
    if meta.env_vars:
        b.append("- **환경변수** (실행 전 값 설정 필요):")
        b.extend(f"  - `{n}` = {_TODO}" for n in meta.env_vars)
    else:
        b.append(f"- **환경변수**: {_NA} (코드에서 감지된 항목 없음)")
    b.append(f"- **포트**: {', '.join(meta.ports) if meta.ports else _NA}")
    b.append("")

    # 4. 실행 방법
    b.append("## 4. 실행 방법")
    if meta.run_entries:
        b.extend(f"- **[{e.kind}]** {e.detail}" for e in meta.run_entries)
    else:
        b.append(f"- {_todo('빌드/실행 명령을 적으세요 (예: `python main.py`, `docker compose up`)')}")
    b.append("")

    # 5. 동작 확인 (자동 감지 불가 → 항상 직접 작성)
    b.append("## 5. 동작 확인")
    b.append(f"- {_todo('정상 동작 확인 방법을 적으세요 (예: 헬스체크 URL, 테스트 명령, 기대 출력)')}")
    b.append("")

    # 6. 주의사항
    b.append("## 6. 주의사항")
    if meta.sensitive:
        b.append("**⚠️ 민감정보 의심 (공유 전 확인):**")
        b.extend(_sensitive_table(meta))
        b.append("> 값은 마스킹됨. 하드코딩된 값은 환경변수/시크릿 매니저로 분리 권장.")
    if meta.notes:
        b.extend(f"- {n}" for n in meta.notes)
    if not meta.sensitive and not meta.notes:
        b.append(f"- {_NA} (자동 분석에서 특이사항 없음 — 직접 검토 권장)")
    b.append("")

    # 7. 디렉터리 구조
    b.append("## 7. 디렉터리 구조")
    b.append(f"- 분석 대상 파일: 총 {len(meta.files)}개")
    b.append("")
    b.append("```")
    b.append(meta.tree or _TODO)
    b.append("```")
    b.append("")

    if diff_md is not None:
        b.append("## 변경 사항 (이전 분석 대비)")
        b.append(diff_md)
        b.append("")

    return _assemble(meta.name, generated_on, b)


def _render_file_markdown(meta, diff_md=None, generated_on=None) -> str:
    """단일 파일용 — 개요 → 코드 분석 → 주의 → 미리보기."""
    b: list[str] = []
    c = meta.code

    # 1. 파일 개요
    b.append("## 1. 파일 개요")
    b.append(f"- **파일명**: {meta.name}")
    b.append(f"- **출처**: `{meta.root}`")
    b.append(f"- **언어**: {', '.join(meta.languages) if meta.languages else '비코드/미상'}")
    if c:
        b.append(f"- **코드 줄 수**: {c.loc}줄")
        b.append(f"- **설명(주석 기반)**: {c.description if c.description else _todo('이 파일의 역할을 적으세요')}")
    b.append("")

    # 2. 코드 분석
    b.append("## 2. 코드 분석 (무엇을 하는 코드인가)")
    if c:
        b.extend(f"- {s}" for s in c.summary)
        b.append("")
        b.append("### 구조")
        b.append(f"- 임포트/의존: {', '.join(c.imports) if c.imports else _NA}")
        b.append(f"- 클래스: {', '.join(c.classes) if c.classes else _NA}")
        b.append(f"- 함수/메서드: {', '.join(c.functions) if c.functions else _NA}")
        b.append(f"- 실행 진입점: {'있음 (단독 실행 가능 추정)' if c.has_entrypoint else '없음 (모듈/라이브러리 추정)'}")
    else:
        b.append(f"- {_NA} (코드 파일이 아니거나 내용 분석을 생략함 — 바이너리/문서 파일)")
    b.append("")

    # 3. 주의사항
    b.append("## 3. 주의사항")
    if meta.sensitive:
        b.append("**⚠️ 민감정보 의심 (공유 전 확인):**")
        b.extend(_sensitive_table(meta))
    b.append(f"- 참조 환경변수: {', '.join(meta.env_vars) if meta.env_vars else _NA}")
    b.append(f"- 감지된 포트: {', '.join(meta.ports) if meta.ports else _NA}")
    if meta.notes:
        b.extend(f"- {n}" for n in meta.notes)
    b.append("")

    # 4. 내용 미리보기
    b.append("## 4. 내용 미리보기")
    b.append("```")
    b.append(meta.readme_excerpt or _NA)
    b.append("```")
    b.append("")

    if diff_md is not None:
        b.append("## 변경 사항 (이전 분석 대비)")
        b.append(diff_md)
        b.append("")

    return _assemble(meta.name, generated_on, b)
