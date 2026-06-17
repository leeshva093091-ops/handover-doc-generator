"""소스 해석 → 분석 → 문서 렌더링을 한 번에 수행하는 진입 함수.

CLI와 웹 화면이 동일한 경로를 쓰도록 한 곳에 모은다 (동작 불일치 방지).
"""

from __future__ import annotations

from . import source
from .analyzer import analyze_project
from .models import ProjectMetadata
from .template import render_markdown


def generate_document(source_str: str) -> tuple[str, ProjectMetadata]:
    """로컬 경로 또는 Git URL을 받아 (인수인계 문서, 메타데이터)를 반환한다.

    실패 시 source.SourceError / PermissionError / OSError를 그대로 올린다 (호출 측이 처리).
    URL 클론 등 임시 자원은 여기서 반드시 정리한다.
    """
    resolved = source.resolve(source_str)
    try:
        meta = analyze_project(
            resolved.path, display_name=resolved.name, origin=resolved.origin
        )
        return render_markdown(meta), meta
    finally:
        resolved.cleanup()
