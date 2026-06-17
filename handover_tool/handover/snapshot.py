"""분석 결과 스냅샷 저장 및 재분석 diff (3단계).

인수인계 문서는 배포/마무리 때마다 갱신되는데(PRD 2단계 사용맥락), 매번 '뭐가 바뀌었는지'를
손으로 비교하기 어렵다. 분석 결과를 JSON 스냅샷으로 남겨두고 다음 실행 때 의미 단위로 비교해
'변경 사항' 섹션을 만든다 (텍스트 diff보다 추가/제거 항목이 또렷하게 보임).

표준 라이브러리(json)만 사용한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import ProjectMetadata

SNAPSHOT_VERSION = 1

# 비교 대상 필드: (스냅샷 키, 사람이 읽는 라벨). 각 값은 비교 가능한 문자열 리스트로 보관.
_DIFF_FIELDS = [
    ("languages", "주요 언어"),
    ("dependencies", "의존성"),
    ("run_entries", "실행 방법"),
    ("ports", "포트"),
    ("env_vars", "환경변수"),
    ("sensitive", "민감정보 의심"),
]


def to_snapshot(meta: ProjectMetadata) -> dict:
    """메타데이터를 비교 가능한 JSON 직렬화용 dict로 변환한다."""
    return {
        "version": SNAPSHOT_VERSION,
        "name": meta.name,
        "origin": meta.root,
        "languages": list(meta.languages),
        # 의존성은 '출처: 항목' 형태로 평탄화해 set 비교가 가능하게 한다.
        "dependencies": [f"{g.source}: {item}" for g in meta.dependencies for item in g.items],
        "run_entries": [f"{e.kind}: {e.detail}" for e in meta.run_entries],
        "ports": list(meta.ports),
        "env_vars": list(meta.env_vars),
        # 민감정보는 위치+종류로 식별 (마스킹값은 매번 같으므로 제외해도 식별 가능).
        "sensitive": [f"{s.kind} @ {s.file}:{s.line}" for s in meta.sensitive],
    }


def save(path: Path, snap: dict) -> None:
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")


def load(path: Path) -> dict | None:
    """이전 스냅샷을 읽는다. 없으면 None, 손상됐으면 ValueError."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"스냅샷을 읽을 수 없습니다: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("스냅샷 형식이 올바르지 않습니다.")
    return data


@dataclass
class DiffResult:
    # 라벨 -> (추가된 항목, 제거된 항목)
    changes: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.changes

    def has_new_sensitive(self) -> bool:
        added, _ = self.changes.get("민감정보 의심", ([], []))
        return bool(added)


def diff(old: dict, new: dict) -> DiffResult:
    """이전/현재 스냅샷을 비교해 필드별 추가·제거 항목을 만든다."""
    result = DiffResult()
    for key, label in _DIFF_FIELDS:
        old_set = set(old.get(key, []) or [])
        new_set = set(new.get(key, []) or [])
        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)
        if added or removed:
            result.changes[label] = (added, removed)
    return result


def render_diff_md(d: DiffResult) -> str:
    """변경 사항을 Markdown 본문으로 만든다 (template이 섹션으로 감싼다)."""
    if d.is_empty():
        return "- 이전 분석과 비교해 변경된 항목이 없습니다."

    lines: list[str] = []
    if d.has_new_sensitive():
        lines.append("> ⚠️ **새로 발견된 민감정보 의심 항목이 있습니다. 우선 확인하세요.**")
        lines.append("")
    for label, (added, removed) in d.changes.items():
        lines.append(f"### {label}")
        lines.extend(f"- ➕ 추가: `{item}`" for item in added)
        lines.extend(f"- ➖ 제거: `{item}`" for item in removed)
        lines.append("")
    return "\n".join(lines).rstrip()
