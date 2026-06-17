"""단일 코드 파일의 정적(휴리스틱) 분석 — "이 코드가 무엇을 하는가"를 유추한다.

LLM 없이 정규식으로 임포트·클래스·함수·진입점을 뽑고, 파일 상단 주석/독스트링을
설명으로 사용한다. 정확한 의미 분석이 아니라 '추정'이며, summary에 근거를 함께 남긴다.
표준 라이브러리(re)만 사용한다.
"""

from __future__ import annotations

import re

from .models import CodeInsight

# 언어별 패턴: 한 줄 단위로 검사.
_PATTERNS = {
    "Python": {
        "import": re.compile(r"^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)"),
        "class": re.compile(r"^\s*class\s+(\w+)"),
        "func": re.compile(r"^\s*(?:async\s+)?def\s+(\w+)"),
        "entry": re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]"),
    },
    "Java": {
        "import": re.compile(r"^\s*import\s+([\w.]+)\s*;"),
        "class": re.compile(r"\b(?:class|interface|enum)\s+(\w+)"),
        "func": re.compile(r"(?:public|private|protected)\s+[\w<>\[\],\s]+?\s+(\w+)\s*\("),
        "entry": re.compile(r"public\s+static\s+void\s+main\s*\("),
    },
    "JavaScript": {
        "import": re.compile(r"^\s*(?:import\s.*from\s+['\"]([^'\"]+)|.*require\(\s*['\"]([^'\"]+))"),
        "class": re.compile(r"\bclass\s+(\w+)"),
        "func": re.compile(r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()"),
        "entry": re.compile(r"\b(?:addEventListener\(|app\.listen\(|main\(\))"),
    },
}
_PATTERNS["TypeScript"] = _PATTERNS["JavaScript"]


def _first_group(match: re.Match) -> str:
    for g in match.groups():
        if g:
            return g
    return ""


def _extract_description(text: str, language: str) -> str:
    """파일 상단의 주석/독스트링에서 설명 한 줄을 뽑는다."""
    stripped = text.lstrip()
    # Python 모듈 독스트링
    if language == "Python":
        m = re.match(r'^[ru]?(?P<q>"""|\'\'\')(?P<body>.*?)(?P=q)', stripped, re.DOTALL)
        if m:
            for line in m.group("body").splitlines():
                if line.strip():
                    return line.strip()[:200]
    # 블록 주석 /** ... */ 또는 /* ... */
    m = re.match(r"/\*\*?(?P<body>.*?)\*/", stripped, re.DOTALL)
    if m:
        for line in m.group("body").splitlines():
            cleaned = line.strip().lstrip("*").strip()
            if cleaned:
                return cleaned[:200]
    # 연속된 줄 주석(//, #)
    for line in stripped.splitlines():
        s = line.strip()
        if s.startswith("//") or s.startswith("#"):
            cleaned = s.lstrip("/#").strip()
            if cleaned:
                return cleaned[:200]
        elif s:
            break  # 코드가 시작되면 중단
    return ""


def analyze_code(text: str, language: str) -> CodeInsight:
    """코드 텍스트를 받아 구조와 유추 요약을 만든다."""
    insight = CodeInsight(language=language)
    lines = text.splitlines()
    insight.loc = sum(1 for line in lines if line.strip())
    insight.description = _extract_description(text, language)

    pats = _PATTERNS.get(language)
    if pats:
        imports, classes, functions = [], [], []
        for line in lines:
            mi = pats["import"].search(line)
            if mi:
                name = _first_group(mi)
                if name and name not in imports:
                    imports.append(name)
            mc = pats["class"].search(line)
            if mc:
                classes.append(mc.group(1))
            mf = pats["func"].search(line)
            if mf:
                fname = _first_group(mf)
                # 언어 키워드 오탐 방지
                if fname and fname not in ("if", "for", "while", "switch", "catch", "return"):
                    functions.append(fname)
            if pats["entry"].search(line):
                insight.has_entrypoint = True
        # 중복 제거(순서 유지)
        insight.imports = list(dict.fromkeys(imports))
        insight.classes = list(dict.fromkeys(classes))
        insight.functions = list(dict.fromkeys(functions))

    insight.summary = _build_summary(insight)
    return insight


def _build_summary(c: CodeInsight) -> list[str]:
    """추출 결과로부터 '무엇을 하는 코드인지' 유추 요약을 만든다 (휴리스틱)."""
    s: list[str] = []
    if c.description:
        s.append(f"설명(주석 기반): {c.description}")
    structure = []
    if c.classes:
        structure.append(f"클래스 {len(c.classes)}개")
    if c.functions:
        structure.append(f"함수/메서드 {len(c.functions)}개")
    if structure:
        s.append("구성: " + ", ".join(structure) + f" (코드 {c.loc}줄)")
    else:
        s.append(f"코드 {c.loc}줄")
    if c.has_entrypoint:
        s.append("실행 진입점(main 등)이 있어 단독 실행되는 코드로 보입니다.")
    else:
        s.append("실행 진입점이 없어 다른 코드에서 가져다 쓰는 모듈/라이브러리로 보입니다.")
    if c.imports:
        preview = ", ".join(c.imports[:6])
        more = " 등" if len(c.imports) > 6 else ""
        s.append(f"외부 의존: {preview}{more}")
    s.append("※ 정적 분석(휴리스틱) 결과로 실제 동작과 다를 수 있어 확인이 필요합니다.")
    return s
