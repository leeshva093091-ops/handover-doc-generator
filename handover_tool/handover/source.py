"""입력 소스(로컬 폴더 또는 Git 저장소 URL)를 분석 가능한 로컬 디렉터리로 해석한다 (2-3).

폐쇄망 내부 GitHub(Enterprise 포함)는 `git clone`이 표준 접근 경로이므로 이를 1차 방식으로
사용한다. git이 없으면 추측으로 다른 방식을 시도하지 않고, 사용자가 직접 클론 후 로컬 경로로
넘기도록 명확히 안내한다(확실하지 않은 동작을 단정하지 않는다).

표준 라이브러리(subprocess/tempfile/shutil)만 사용한다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# 얕은 클론에 거는 시간 제한(초). 폐쇄망 내부망 기준 넉넉히.
_CLONE_TIMEOUT = 180

# URL 판별: scheme://... , git@host:... , 또는 .git 으로 끝나는 경우.
_URL_RE = re.compile(r"^(?:https?|git|ssh)://|^git@", re.IGNORECASE)


class SourceError(Exception):
    """소스를 해석할 수 없을 때(잘못된 경로/URL, git 부재, 클론 실패 등)."""


@dataclass
class ResolvedSource:
    path: Path  # 실제 분석 대상 로컬 디렉터리
    name: str  # 표시용 프로젝트명
    origin: str  # 표시용 출처 (로컬 경로 또는 원본 URL)
    cleanup: Callable[[], None]  # 임시 디렉터리 정리 (로컬 경로면 no-op)


def is_url(source: str) -> bool:
    """입력이 Git 저장소 URL이면 True."""
    s = source.strip()
    return bool(_URL_RE.search(s)) or s.endswith(".git")


def repo_name_from_url(url: str) -> str:
    """URL에서 저장소 이름을 뽑는다 (마지막 경로 조각, .git 제거)."""
    cleaned = url.strip().rstrip("/")
    # git@host:owner/repo.git 형태도 처리.
    tail = re.split(r"[/:]", cleaned)[-1]
    if tail.endswith(".git"):
        tail = tail[:-4]
    return tail or "repository"


def _clone_with_git(url: str) -> ResolvedSource:
    """git으로 얕은 클론 후 ResolvedSource를 반환한다."""
    if shutil.which("git") is None:
        raise SourceError(
            "git이 설치되어 있지 않습니다. git을 설치하거나, 저장소를 직접 클론한 뒤 "
            "로컬 폴더 경로로 분석하세요."
        )

    tmpdir = tempfile.mkdtemp(prefix="handover_clone_")

    def cleanup() -> None:
        # 분석이 끝나면 임시 클론을 지운다. 실패해도 본 작업을 막지 않는다.
        shutil.rmtree(tmpdir, ignore_errors=True)

    try:
        # `--` 로 옵션/URL 경계를 명시해 '-'로 시작하는 인자 주입을 막는다.
        # shell=False(리스트 인자)라 셸 인젝션 위험도 없다.
        subprocess.run(
            ["git", "clone", "--depth", "1", "--", url, tmpdir],
            check=True,
            capture_output=True,
            text=True,
            timeout=_CLONE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        cleanup()
        raise SourceError(f"저장소 클론이 {_CLONE_TIMEOUT}초 안에 끝나지 않았습니다: {url}")
    except subprocess.CalledProcessError as exc:
        cleanup()
        # git의 stderr를 그대로 전달해 인증/주소 문제를 사용자가 바로 알 수 있게 한다.
        detail = (exc.stderr or "").strip() or "원인 불명"
        raise SourceError(f"저장소 클론 실패: {url}\n  git: {detail}")
    except OSError as exc:
        cleanup()
        raise SourceError(f"git 실행 중 문제가 발생했습니다: {exc}")

    return ResolvedSource(
        path=Path(tmpdir),
        name=repo_name_from_url(url),
        origin=url,
        cleanup=cleanup,
    )


def _resolve_local(source: str) -> ResolvedSource:
    """로컬 경로(폴더 또는 단일 파일)를 검증해 ResolvedSource로 만든다."""
    root = Path(source).expanduser()
    if not root.exists():
        raise SourceError(f"경로가 존재하지 않습니다 → {root}")
    # 폴더와 단일 파일을 모두 허용한다 (자바·문서 파일 등 개별 분석 지원).
    # '.'/'..' 처럼 name이 비는 경우 절대경로 기준 이름으로 보정.
    name = root.name or root.resolve().name
    return ResolvedSource(
        path=root,
        name=name,
        origin=str(root),
        cleanup=lambda: None,
    )


def resolve(source: str) -> ResolvedSource:
    """로컬 경로 또는 Git URL을 받아 분석 가능한 디렉터리로 해석한다.

    URL이면 임시 디렉터리에 클론한다. 호출 측은 분석 후 반드시 result.cleanup()을 호출해야 한다.
    """
    if is_url(source):
        return _clone_with_git(source)
    return _resolve_local(source)
