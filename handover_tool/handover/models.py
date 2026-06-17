"""분석 결과를 담는 데이터 구조.

분석 단계(analyzer)와 출력 단계(template)를 이 모델로 분리해, 양식이 바뀌어도
분석 로직을 건드리지 않도록 한다 (정형 양식 출력 = 도구의 핵심 가치).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DependencyGroup:
    """의존성 파일 하나에서 뽑아낸 묶음."""

    source: str  # 예: "requirements.txt", "package.json"
    items: list[str] = field(default_factory=list)


@dataclass
class RunEntry:
    """실행 방법 후보 한 줄."""

    kind: str  # 예: "Python 진입점", "셸 스크립트", "Make 타깃", "Docker"
    detail: str


@dataclass
class SensitiveFinding:
    """민감정보로 의심되는 항목 한 건 (2단계 주의사항 추출).

    오탐 가능성이 있으므로 confidence로 신뢰도를 함께 남기고(PRD 위험요소 2),
    값은 절대 원본 그대로 두지 않고 masked만 보관한다.
    """

    kind: str  # 예: "하드코딩된 비밀번호 의심", "DB 접속 문자열", "개인키"
    file: str  # 프로젝트 루트 기준 상대 경로
    line: int
    masked: str  # 마스킹된 미리보기 (원본 값 노출 금지)
    confidence: str  # "높음" / "중간" / "낮음"


@dataclass
class ProjectMetadata:
    """프로젝트 한 개에 대한 분석 결과 전체."""

    name: str
    root: str
    languages: list[str] = field(default_factory=list)
    readme_path: str | None = None
    readme_excerpt: str | None = None
    dependencies: list[DependencyGroup] = field(default_factory=list)
    run_entries: list[RunEntry] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)  # 실행 전 준비/환경 (도출값)
    ports: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)  # 분석 대상 파일(상대경로, 잡음 디렉터리 제외)
    env_vars: list[str] = field(default_factory=list)  # 실행에 필요한 환경변수 이름
    sensitive: list[SensitiveFinding] = field(default_factory=list)  # 민감정보 의심 항목
    tree: str = ""
    # 자동 추출이 빗나갈 수 있으므로(PRD 위험요소 1), 사람이 보정해야 할 지점을 모아 둔다.
    notes: list[str] = field(default_factory=list)
