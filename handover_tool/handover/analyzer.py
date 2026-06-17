"""프로젝트 폴더를 읽어 메타데이터를 뽑아내는 자동 분석기 (도구의 심장).

표준 라이브러리만 사용한다. 분석이 완벽할 수 없으므로(프로젝트 구조가 제각각),
못 찾은 항목은 예외로 죽이지 않고 metadata.notes에 "확인 필요"로 남긴다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import codeinsight, secrets
from .models import DependencyGroup, ProjectMetadata, RunEntry, SensitiveFinding

# 트리/언어 통계에서 제외할 잡음 디렉터리 (분석 가치가 낮고 양이 많음).
IGNORED_DIRS = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", "venv", ".venv",
    "env", ".env", "dist", "build", ".idea", ".vscode", ".pytest_cache",
    ".mypy_cache", "target", "out", ".gradle", "vendor",
}

# 확장자 → 사람이 읽는 언어 이름.
LANGUAGE_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".java": "Java", ".go": "Go", ".rb": "Ruby", ".rs": "Rust",
    ".c": "C", ".cpp": "C++", ".cs": "C#", ".php": "PHP",
    ".kt": "Kotlin", ".swift": "Swift", ".scala": "Scala",
    ".sh": "Shell", ".sql": "SQL",
}

# 흔한 실행 진입점 후보 (파일명 → 설명).
ENTRYPOINT_FILES = {
    "manage.py": "Django 관리 명령 (python manage.py runserver 등)",
    "main.py": "Python 진입점 (python main.py)",
    "app.py": "Python 앱 진입점 (python app.py)",
    "wsgi.py": "WSGI 진입점 (gunicorn/uwsgi 등으로 구동)",
    "index.js": "Node 진입점 (node index.js)",
    "server.js": "Node 서버 진입점 (node server.js)",
}

# 포트로 보이는 숫자를 찾기 위한 패턴. 오탐 가능성이 있어 notes로 검증을 유도한다.
PORT_PATTERN = re.compile(r"\b(?:port|PORT)\s*[=:]\s*['\"]?(\d{2,5})")


def read_text(path: Path, limit: int | None = None) -> str:
    """텍스트 파일을 안전하게 읽는다.

    한글 Windows 환경을 고려해 utf-8(BOM 자동 제거) → cp949 순으로 시도하고, 그래도
    실패하면 깨진 문자를 대체해 읽는다 (분석 도구가 인코딩 때문에 멈추면 안 됨).
    utf-8-sig를 먼저 써서 BOM(﻿)이 첫 줄 인식을 깨지 않게 한다.
    """
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    return text[:limit] if limit else text


def _scan_files(root: Path) -> list[Path]:
    """잡음 디렉터리를 건너뛰며 전체 파일 목록을 모은다."""
    files: list[Path] = []
    for path in root.rglob("*"):
        # 경로 어딘가에 무시 대상 디렉터리가 끼어 있으면 제외.
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def detect_languages(files: list[Path]) -> list[str]:
    """확장자 빈도를 세어 많이 쓰인 언어 순으로 반환."""
    counts: dict[str, int] = {}
    for f in files:
        lang = LANGUAGE_BY_EXT.get(f.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return [lang for lang, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)]


def find_readme(root: Path) -> tuple[Path | None, str | None]:
    """README를 찾아 앞부분 일부를 발췌한다 (개요 슬롯에 사용)."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        candidate = root / name
        if candidate.exists():
            text = read_text(candidate).strip()
            # 너무 길면 인수인계 문서가 비대해지므로 앞부분만.
            excerpt = "\n".join(text.splitlines()[:15]).strip()
            return candidate, excerpt or None
    return None, None


def parse_dependencies(root: Path) -> tuple[list[DependencyGroup], list[str]]:
    """알려진 의존성 파일을 파싱한다. 못 다룬 파일은 notes로 알린다."""
    groups: list[DependencyGroup] = []
    notes: list[str] = []

    # requirements.txt: 한 줄 = 한 의존성. 주석/빈 줄 제외.
    req = root / "requirements.txt"
    if req.exists():
        items = [
            line.strip()
            for line in read_text(req).splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        groups.append(DependencyGroup(source="requirements.txt", items=items))

    # package.json: dependencies/devDependencies + scripts 힌트.
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(read_text(pkg))
            deps = list((data.get("dependencies") or {}).keys())
            dev = list((data.get("devDependencies") or {}).keys())
            items = deps + [f"{d} (dev)" for d in dev]
            groups.append(DependencyGroup(source="package.json", items=items))
        except json.JSONDecodeError:
            notes.append("package.json 파싱 실패 — 형식을 직접 확인하세요.")

    # 그 외 의존성 파일은 '존재'만 알리고 상세 파싱은 추후 단계로 미룬다.
    for name, hint in (
        ("pyproject.toml", "Python 프로젝트 메타/의존성"),
        ("Pipfile", "pipenv 의존성"),
        ("pom.xml", "Maven 의존성"),
        ("build.gradle", "Gradle 의존성"),
        ("go.mod", "Go 모듈 의존성"),
        ("Gemfile", "Ruby 의존성"),
        ("Cargo.toml", "Rust 의존성"),
    ):
        if (root / name).exists():
            groups.append(DependencyGroup(source=name, items=[f"({hint} — 상세는 파일 확인)"]))

    return groups, notes


def find_run_entries(root: Path, files: list[Path]) -> list[RunEntry]:
    """실행/구동 방법 후보를 모은다."""
    entries: list[RunEntry] = []

    # 루트의 알려진 진입점 파일.
    for name, desc in ENTRYPOINT_FILES.items():
        if (root / name).exists():
            entries.append(RunEntry(kind="진입점", detail=f"{name} — {desc}"))

    # 셸 스크립트 (루트 우선).
    for script in sorted(root.glob("*.sh")):
        entries.append(RunEntry(kind="셸 스크립트", detail=f"{script.name} — bash {script.name}"))

    # Makefile 타깃.
    makefile = root / "Makefile"
    if makefile.exists():
        targets = re.findall(r"^([a-zA-Z0-9_.-]+):", read_text(makefile), flags=re.MULTILINE)
        detail = ", ".join(targets[:10]) if targets else "타깃 확인 필요"
        entries.append(RunEntry(kind="Make", detail=f"make 타깃: {detail}"))

    # Docker 관련.
    if (root / "Dockerfile").exists():
        entries.append(RunEntry(kind="Docker", detail="Dockerfile — docker build/run"))
    for compose in ("docker-compose.yml", "docker-compose.yaml", "compose.yml"):
        if (root / compose).exists():
            entries.append(RunEntry(kind="Docker", detail=f"{compose} — docker compose up"))

    # package.json scripts.
    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(read_text(pkg)).get("scripts") or {}
            for name in scripts:
                entries.append(RunEntry(kind="npm script", detail=f"npm run {name}"))
        except json.JSONDecodeError:
            pass  # 의존성 파싱 단계에서 이미 note 추가됨.

    return entries


# 텍스트로 열어 패턴 검사할 확장자 (코드/설정 파일).
SCANNABLE_EXTS = {*LANGUAGE_BY_EXT, ".env", ".yml", ".yaml", ".ini", ".cfg",
                  ".conf", ".json", ".properties", ".toml", ".xml", ".txt"}
_MAX_SCAN_BYTES = 1_000_000  # 너무 큰 파일은 성능상 건너뜀


def scan_text_files(
    root: Path, files: list[Path]
) -> tuple[list[str], list[str], list[SensitiveFinding]]:
    """텍스트 파일을 한 번씩만 읽어 포트·환경변수·민감정보를 함께 추출한다.

    파일을 여러 번 여는 비용을 줄이려고 단일 루프로 묶었다.
    반환: (정렬된 포트, 정렬된 환경변수 이름, 민감정보 의심 항목 목록)
    """
    ports: set[str] = set()
    env_vars: set[str] = set()
    sensitive: list[SensitiveFinding] = []

    for f in files:
        if f.suffix.lower() not in SCANNABLE_EXTS:
            continue
        try:
            if f.stat().st_size > _MAX_SCAN_BYTES:
                continue
        except OSError:
            continue

        text = read_text(f)
        try:
            relpath = str(f.relative_to(root))
        except ValueError:
            relpath = f.name

        for match in PORT_PATTERN.finditer(text):
            ports.add(match.group(1))
        env_vars |= secrets.find_env_vars(text)
        sensitive.extend(secrets.scan_text(relpath, text))

    return sorted(ports, key=int), sorted(env_vars), sensitive


def build_tree(root: Path, display_name: str | None = None, max_depth: int = 2) -> str:
    """상위 몇 단계 디렉터리 구조를 텍스트 트리로 만든다 (구조 파악용).

    display_name을 주면 트리 최상단 라벨로 쓴다 (임시 클론 폴더명 대신 저장소명 표시 등).
    """
    lines: list[str] = [(display_name or root.name) + "/"]

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(
                (p for p in directory.iterdir() if p.name not in IGNORED_DIRS),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except OSError:
            return
        for i, entry in enumerate(entries):
            connector = "└── " if i == len(entries) - 1 else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")
            if entry.is_dir():
                extension = "    " if i == len(entries) - 1 else "│   "
                walk(entry, prefix + extension, depth + 1)

    walk(root, "", 1)
    return "\n".join(lines)


# 의존성 파일 → (런타임 준비 문구, 설치 명령 힌트)
_RUNTIME_HINTS = {
    "requirements.txt": ("Python 런타임 설치", "pip install -r requirements.txt"),
    "pyproject.toml": ("Python 런타임 설치", "pip install ."),
    "Pipfile": ("Python 런타임 설치", "pipenv install"),
    "package.json": ("Node.js 런타임 설치", "npm install"),
    "pom.xml": ("JDK(Java) 설치", "mvn install"),
    "build.gradle": ("JDK(Java) 설치", "gradle build"),
    "go.mod": ("Go 설치", "go mod download"),
    "Gemfile": ("Ruby 설치", "bundle install"),
    "Cargo.toml": ("Rust 툴체인 설치", "cargo build"),
}


def derive_prerequisites(meta: ProjectMetadata) -> list[str]:
    """분석 결과에서 '실행 전 준비사항'을 도출한다 (설치/실행 영역 고도화).

    런타임·의존성 설치 명령·Docker·환경변수·포트·외부 접속정보 등 사람이 인계받아
    바로 띄우기 위해 확인해야 할 항목을 한데 모은다. 중복은 제거하고 순서를 유지한다.
    """
    items: list[str] = []
    sources = {g.source for g in meta.dependencies}

    # 런타임 + 의존성 설치 명령
    for source_name, (runtime, install_cmd) in _RUNTIME_HINTS.items():
        if source_name in sources:
            items.append(runtime)
            items.append(f"의존성 설치: `{install_cmd}`  ({source_name})")

    # Docker 사용 여부 (실행 방법에서 감지)
    if any(e.kind == "Docker" for e in meta.run_entries):
        items.append("Docker 설치 및 데몬 실행")

    # 환경변수
    if meta.env_vars:
        items.append(f"환경변수 {len(meta.env_vars)}개 설정: " + ", ".join(meta.env_vars))

    # 포트
    if meta.ports:
        items.append("포트 개방/충돌 확인: " + ", ".join(meta.ports))

    # DB/외부 서비스 접속정보
    if any("접속 문자열" in s.kind for s in meta.sensitive):
        items.append("DB/외부 서비스 접속 정보 준비 (코드의 접속 문자열 확인 — 민감정보 표 참고)")

    # 중복 제거(순서 유지)
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]


def _read_if_text(path: Path) -> tuple[bool, str]:
    """텍스트 파일이면 (True, 내용), 아니면(바이너리/과대/오류) (False, "")."""
    try:
        if path.stat().st_size > _MAX_SCAN_BYTES:
            return False, ""
        head = path.read_bytes()[:4096]
    except OSError:
        return False, ""
    if b"\x00" in head:  # NUL 바이트 → 바이너리로 간주
        return False, ""
    return True, read_text(path)


def analyze_file(path: Path, name: str, origin: str) -> ProjectMetadata:
    """단일 파일을 분석한다 (자바·문서 등 개별 파일 인계용)."""
    meta = ProjectMetadata(name=name, root=origin, kind="file", files=[path.name])
    lang = LANGUAGE_BY_EXT.get(path.suffix.lower())
    if lang:
        meta.languages = [lang]

    is_text, text = _read_if_text(path)
    if is_text:
        # 내용 미리보기(앞부분) — 개요의 'README 발췌' 슬롯을 파일 미리보기로 활용
        meta.readme_excerpt = "\n".join(text.splitlines()[:15]).strip() or None
        meta.ports = sorted({m.group(1) for m in PORT_PATTERN.finditer(text)}, key=int)
        meta.env_vars = sorted(secrets.find_env_vars(text))
        meta.sensitive = secrets.scan_text(path.name, text)
        # 코드 파일이면 "무엇을 하는 코드인지" 정적 분석.
        if lang:
            meta.code = codeinsight.analyze_code(text, lang)
            if meta.code.has_entrypoint and path.name in ENTRYPOINT_FILES:
                meta.run_entries = [RunEntry(kind="진입점",
                                             detail=f"{path.name} — {ENTRYPOINT_FILES[path.name]}")]
    else:
        meta.notes.append("바이너리/비텍스트(또는 너무 큰) 파일 — 내용 분석을 생략했습니다.")

    meta.tree = path.name
    meta.prerequisites = derive_prerequisites(meta)
    if is_text:
        meta.notes.append("단일 파일 분석입니다. 전체 프로젝트 맥락은 포함되지 않습니다.")
    return meta


def analyze_project(
    root: Path, display_name: str | None = None, origin: str | None = None
) -> ProjectMetadata:
    """경로(폴더 또는 단일 파일)를 받아 전체 메타데이터를 조립한다.

    display_name/origin은 표시용 값 — URL 클론 시 임시 폴더가 아니라 저장소명/URL이
    문서에 보이도록 주입한다. 생략하면 로컬 경로 기준으로 채운다.
    """
    # 단일 파일이면 파일 전용 분석으로 분기.
    if root.is_file():
        return analyze_file(root, display_name or root.name, origin or str(root))

    files = _scan_files(root)

    name = display_name or root.name
    # 분석 대상 파일 목록(상대경로, forward slash로 정규화).
    rel_files = sorted(f.relative_to(root).as_posix() for f in files)
    readme_path, readme_excerpt = find_readme(root)
    dependencies, dep_notes = parse_dependencies(root)
    run_entries = find_run_entries(root, files)
    ports, env_vars, sensitive = scan_text_files(root, files)

    meta = ProjectMetadata(
        name=name,
        root=origin or str(root),
        languages=detect_languages(files),
        readme_path=str(readme_path) if readme_path else None,
        readme_excerpt=readme_excerpt,
        dependencies=dependencies,
        run_entries=run_entries,
        ports=ports,
        files=rel_files,
        env_vars=env_vars,
        sensitive=sensitive,
        tree=build_tree(root, display_name=name),
        notes=list(dep_notes),
    )

    # 준비사항은 위 항목들에서 도출 (설치/실행 영역 고도화).
    meta.prerequisites = derive_prerequisites(meta)

    # 핵심 정보가 비었으면 사람이 채우도록 명시 (빈 문서로 오해하지 않게).
    if not meta.readme_excerpt:
        meta.notes.append("README를 찾지 못함 — 프로젝트 개요를 직접 작성하세요.")
    if not meta.run_entries:
        meta.notes.append("실행 방법을 자동으로 찾지 못함 — 실행 절차를 직접 작성하세요.")
    if not meta.dependencies:
        meta.notes.append("의존성 파일을 찾지 못함 — 설치 절차를 직접 확인하세요.")
    if meta.sensitive:
        meta.notes.append(
            f"민감정보 의심 {len(meta.sensitive)}건 발견 — 아래 '민감정보' 표를 확인하고 "
            "문서 공유 전 처리하세요(코드에서 분리/환경변수화 등)."
        )

    return meta
