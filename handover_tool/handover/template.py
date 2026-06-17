"""메타데이터를 정형 인수인계 문서(Markdown)로 렌더링한다.

핵심 가치: 무엇을 넣든 '항상 같은 섹션 구조'로 나오게 한다. 값이 비어도 슬롯을
없애지 않고 '확인 필요' 안내를 채워, 후임자가 무엇이 빠졌는지 바로 알 수 있게 한다.
"""

from __future__ import annotations

from .models import ProjectMetadata

# 정형 양식의 고정 섹션 순서 (개요 → 설치 → 실행 → 환경 → 주의사항).
_PLACEHOLDER = "_확인 필요 — 직접 작성하세요._"


def _bullet(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else _PLACEHOLDER


def render_markdown(meta: ProjectMetadata, diff_md: str | None = None) -> str:
    """정형 인수인계 문서를 생성한다. 단일 파일과 프로젝트는 양식이 다르다."""
    if meta.kind == "file":
        return _render_file_markdown(meta, diff_md)
    return _render_project_markdown(meta, diff_md)


def _render_file_markdown(meta: ProjectMetadata, diff_md: str | None = None) -> str:
    """단일 파일용 양식 (개요 → 코드 분석 → 주의사항 → 내용 미리보기)."""
    lines: list[str] = []
    lines.append(f"# 파일 인계 문서 — {meta.name}")
    lines.append("")
    lines.append("> 단일 파일 분석입니다. 자동 추출(정적 분석)은 빗나갈 수 있으니 "
                 "`확인 필요` 항목을 검토하세요.")
    lines.append("")

    # 1. 파일 개요
    lines.append("## 1. 파일 개요")
    lines.append(f"- **파일명**: {meta.name}")
    lines.append(f"- **출처**: `{meta.root}`")
    lines.append(f"- **언어**: {', '.join(meta.languages) if meta.languages else '비코드/미상'}")
    if meta.code:
        lines.append(f"- **코드 줄 수**: {meta.code.loc}줄")
        if meta.code.description:
            lines.append(f"- **설명(주석 기반)**: {meta.code.description}")
    lines.append("")

    # 2. 코드 분석 (코드 파일일 때) — "무엇을 하는 코드인가"
    if meta.code:
        c = meta.code
        lines.append("## 2. 코드 분석 (무엇을 하는 코드인가)")
        lines.append(_bullet(c.summary))
        lines.append("")
        lines.append("### 구조")
        lines.append(f"- 임포트/의존: {', '.join(c.imports) if c.imports else '없음/미검출'}")
        lines.append(f"- 클래스: {', '.join(c.classes) if c.classes else '없음'}")
        lines.append(f"- 함수/메서드: {', '.join(c.functions) if c.functions else '없음'}")
        lines.append(f"- 실행 진입점: {'있음' if c.has_entrypoint else '없음(모듈/라이브러리 추정)'}")
        lines.append("")

    # 3. 주의사항 (민감정보 + 환경/포트 + 메모)
    lines.append("## 3. 주의사항")
    if meta.sensitive:
        lines.append("| 종류 | 위치 | 미리보기(마스킹) | 신뢰도 |")
        lines.append("|---|---|---|---|")
        for f in meta.sensitive:
            lines.append(f"| {f.kind} | `{f.file}:{f.line}` | `{f.masked}` | {f.confidence} |")
        lines.append("")
    if meta.env_vars:
        lines.append(f"- 참조 환경변수: {', '.join(meta.env_vars)}")
    if meta.ports:
        lines.append(f"- 감지된 포트: {', '.join(meta.ports)}")
    lines.append(_bullet(meta.notes) if meta.notes else "- 추가 메모 없음")
    lines.append("")

    # 4. 내용 미리보기
    lines.append("## 4. 내용 미리보기")
    lines.append("```")
    lines.append(meta.readme_excerpt or _PLACEHOLDER)
    lines.append("```")
    lines.append("")

    if diff_md is not None:
        lines.append("## 5. 이전 분석 대비 변경 사항")
        lines.append(diff_md)
        lines.append("")
    return "\n".join(lines)


def _render_project_markdown(meta: ProjectMetadata, diff_md: str | None = None) -> str:
    """프로젝트(폴더/Git)용 정형 양식.

    diff_md가 주어지면(재분석 시) '이전 분석 대비 변경 사항' 섹션을 덧붙인다.
    """
    lines: list[str] = []

    lines.append(f"# 인수인계 문서 — {meta.name}")
    lines.append("")
    lines.append("> 이 문서는 자동 생성되었습니다. 자동 추출이 빗나갈 수 있으니 "
                 "`확인 필요` 항목과 주의사항을 반드시 검토하세요.")
    lines.append("")

    # 1. 개요
    lines.append("## 1. 개요")
    lines.append(f"- **프로젝트명**: {meta.name}")
    lines.append(f"- **출처**: `{meta.root}`")
    lines.append(f"- **주요 언어**: {', '.join(meta.languages) if meta.languages else _PLACEHOLDER}")
    lines.append("")
    if meta.readme_excerpt:
        lines.append("**README 발췌**")
        lines.append("")
        lines.append("```")
        lines.append(meta.readme_excerpt)
        lines.append("```")
    else:
        lines.append(f"**README 발췌**: {_PLACEHOLDER}")
    lines.append("")

    # 2. 설치 (준비사항 + 의존성)
    lines.append("## 2. 설치")
    lines.append("### 준비사항(Prerequisites)")
    lines.append(_bullet(meta.prerequisites))
    lines.append("")
    lines.append("### 의존성")
    if meta.dependencies:
        for group in meta.dependencies:
            lines.append(f"### {group.source}")
            lines.append(_bullet(group.items))
            lines.append("")
    else:
        lines.append(_PLACEHOLDER)
        lines.append("")

    # 3. 실행
    lines.append("## 3. 실행")
    if meta.run_entries:
        for entry in meta.run_entries:
            lines.append(f"- **[{entry.kind}]** {entry.detail}")
    else:
        lines.append(_PLACEHOLDER)
    lines.append("")

    # 4. 환경 (포트, 필요 환경변수)
    lines.append("## 4. 환경")
    lines.append(f"- **감지된 포트**: {', '.join(meta.ports) if meta.ports else '없음/확인 필요'}")
    if meta.env_vars:
        lines.append("- **필요 환경변수** (실행 전 설정 필요):")
        lines.extend(f"  - `{name}`" for name in meta.env_vars)
    else:
        lines.append("- **필요 환경변수**: 자동 감지된 항목 없음 (직접 확인 권장)")
    lines.append("")

    # 5. 주의사항 — 민감정보 의심 항목을 먼저, 그 다음 분석 메모.
    lines.append("## 5. 주의사항")
    if meta.sensitive:
        lines.append("### ⚠️ 민감정보 의심 (문서 공유 전 반드시 확인)")
        lines.append("")
        lines.append("| 종류 | 위치 | 미리보기(마스킹) | 신뢰도 |")
        lines.append("|---|---|---|---|")
        for f in meta.sensitive:
            lines.append(f"| {f.kind} | `{f.file}:{f.line}` | `{f.masked}` | {f.confidence} |")
        lines.append("")
        lines.append("> 실제 비밀값은 마스킹되어 있습니다. 코드에 하드코딩된 값은 "
                     "환경변수/시크릿 매니저로 분리하는 것을 권장합니다.")
        lines.append("")
    if meta.notes:
        lines.append("### 분석 메모")
        lines.append(_bullet(meta.notes))
    elif not meta.sensitive:
        lines.append("- 자동 분석에서 특별히 표시할 항목 없음 (직접 검토 권장).")
    lines.append("")

    # 6. 디렉터리 구조
    lines.append("## 6. 디렉터리 구조")
    lines.append(f"- 분석 대상 파일: 총 {len(meta.files)}개 (잡음 디렉터리 제외)")
    lines.append("")
    lines.append("```")
    lines.append(meta.tree or _PLACEHOLDER)
    lines.append("```")
    lines.append("")

    # 7. 변경 사항 (재분석 시에만)
    if diff_md is not None:
        lines.append("## 7. 이전 분석 대비 변경 사항")
        lines.append(diff_md)
        lines.append("")

    return "\n".join(lines)
