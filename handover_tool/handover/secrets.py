"""민감정보(키·비밀번호·접속정보) 및 필요 환경변수 탐지 (2단계).

설계 원칙:
- 완벽한 탐지는 불가능하므로(PRD 위험요소 2), '의심 항목까지 보수적으로' 넓게 잡되
  신뢰도(confidence)를 함께 남겨 사람이 판단하게 한다.
- 원본 비밀값은 절대 그대로 출력하지 않는다 — 항상 마스킹해서 위치만 알려준다.
- 표준 라이브러리(re)만 사용한다.
"""

from __future__ import annotations

import re

from .models import SensitiveFinding

# 값에 이런 토큰이 들어가면 실제 비밀이 아니라 자리표시자일 확률이 높음 → 신뢰도 낮춤.
_PLACEHOLDER_HINTS = (
    "changeme", "change_me", "your_", "yourpassword", "example", "placeholder",
    "dummy", "xxxx", "<", ">", "...", "todo", "test123", "sample", "fixme",
    "foo", "bar", "abc123", "password123", "secret123", "redacted", "n/a",
    "${", "{{", "env.", "process.env",
)

# 줄 단위로 검사할 패턴: (종류, 정규식, 기본 신뢰도)
# 값 캡처 그룹이 있으면 그 그룹을 마스킹한다.
_LINE_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # 자격증명을 포함한 DB/서비스 접속 문자열: scheme://user:pass@host
    ("접속 문자열(자격증명 포함)",
     re.compile(r"\b\w+://[^\s:'\"]+:([^\s@'\"]+)@[^\s'\"]+"), "높음"),
    # AWS Access Key ID
    ("AWS 액세스 키",
     re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), "높음"),
    # 비밀번호/시크릿/토큰/키를 따옴표 값으로 하드코딩.
    # 식별자 내부 포함(DB_PASSWORD, SECRET_KEY 등)과 JSON 키("password": "...")를 모두 잡도록
    # 키워드 앞뒤에 식별자 문자를 허용하고, 키 다음 따옴표(['"]?)도 선택적으로 받는다.
    ("하드코딩된 비밀값 의심",
     re.compile(r"(?i)[A-Za-z_]*(?:password|passwd|pwd|secret|api[_-]?key|"
                r"access[_-]?key|token|auth)[A-Za-z_]*['\"]?\s*[:=]\s*['\"]([^'\"]{4,})['\"]"),
     "중간"),
    # Bearer 토큰
    ("Bearer 토큰",
     re.compile(r"[Bb]earer\s+([A-Za-z0-9\-_\.]{12,})"), "중간"),
    # JWT (eyJ... 형태)
    ("JWT 토큰",
     re.compile(r"\b(eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]+)"), "높음"),
    # Slack 토큰
    ("Slack 토큰",
     re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})"), "높음"),
    # GitHub 토큰
    ("GitHub 토큰",
     re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})"), "높음"),
    # Google API 키
    ("Google API 키",
     re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,})"), "높음"),
]

# 여러 줄에 걸친 개인키 블록.
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")

# 환경변수 참조 패턴 (실행에 필요한 환경변수 이름을 모은다).
_ENV_PATTERNS = [
    re.compile(r"os\.environ\.get\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([^'\"]+)['\"]\s*\]"),
    re.compile(r"os\.getenv\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"]([^'\"]+)['\"]\s*\]"),
    re.compile(r"System\.getenv\(\s*['\"]([^'\"]+)['\"]"),
]


def mask(value: str) -> str:
    """비밀값을 마스킹한다. 위치 파악용 힌트만 남기고 원본은 가린다."""
    v = value.strip()
    if len(v) <= 4:
        return "*" * len(v)
    return f"{v[:2]}{'*' * (len(v) - 3)}{v[-1]}"


def _adjust_confidence(value: str, base: str) -> str:
    """값이 자리표시자처럼 보이면 신뢰도를 낮춰 오탐 부담을 줄인다."""
    low = value.lower()
    if any(hint in low for hint in _PLACEHOLDER_HINTS):
        return "낮음"
    return base


def scan_text(relpath: str, text: str) -> list[SensitiveFinding]:
    """파일 한 개의 텍스트에서 민감정보 의심 항목을 찾는다."""
    findings: list[SensitiveFinding] = []

    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern, base_conf in _LINE_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            # 캡처 그룹이 있으면 그 값을, 없으면 매치 전체를 마스킹 대상으로.
            value = match.group(1) if match.groups() else match.group(0)
            findings.append(SensitiveFinding(
                kind=kind,
                file=relpath,
                line=lineno,
                masked=mask(value),
                confidence=_adjust_confidence(value, base_conf),
            ))

    # 개인키 블록은 시작 줄 번호만 보고한다.
    key_match = _PRIVATE_KEY_RE.search(text)
    if key_match:
        line = text[:key_match.start()].count("\n") + 1
        findings.append(SensitiveFinding(
            kind="개인키(PRIVATE KEY) 포함",
            file=relpath,
            line=line,
            masked="-----BEGIN ... PRIVATE KEY-----",
            confidence="높음",
        ))

    return findings


def find_env_vars(text: str) -> set[str]:
    """텍스트에서 참조하는 환경변수 이름을 모은다."""
    names: set[str] = set()
    for pattern in _ENV_PATTERNS:
        for match in pattern.finditer(text):
            names.add(match.group(1))
    return names
