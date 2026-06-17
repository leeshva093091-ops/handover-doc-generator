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
    """정형 인수인계 문서 문자열을 생성한다.

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

    # 2. 설치 (의존성)
    lines.append("## 2. 설치")
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
