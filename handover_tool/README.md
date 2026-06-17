# 인수인계 문서 자동 생성기 (GUI)

![version](https://img.shields.io/badge/version-0.4.1-blue.svg)
![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![dependencies](https://img.shields.io/badge/dependencies-none%20(stdlib)-brightgreen.svg)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

프로젝트 폴더·개별 파일·Git URL을 넣으면 **설치·실행·주의사항**을 표·차트가 포함된 정형
문서로 뽑아주는 **데스크톱 GUI 프로그램**. UI(tkinter)와 분석 모두 **외부 패키지 없이
파이썬 표준 라이브러리만** 사용한다.

> **저장소**: https://github.com/leeshva093091-ops/handover-doc-generator
> **바로 실행**: [Releases](https://github.com/leeshva093091-ops/handover-doc-generator/releases)에서 `handover-gui.exe` 다운로드 → 더블클릭 (Python 불필요)
> 기획/진행: 상위 [PRD.md](../PRD.md) · [CHECKLIST.md](../CHECKLIST.md)

## 요구사항
- Python 3.9 이상 (표준 라이브러리만, 추가 설치 불필요) — exe로 받으면 불필요
- (선택) `git` — **Git URL 입력**에만 필요. 폴더/파일 분석에는 불필요. (창 우측 상단에서 Git 사용 가능 여부 표시)

## 실행
```bash
# 소스 실행 (handover_tool 디렉터리에서)
python handover_gui.py
```
실행 시 창은 전체화면 크기로 시작한다. 배포본은 `handover-gui.exe` 더블클릭.

## 사용 흐름 (GUI)
1. **프로젝트 추가** — `프로젝트 찾아보기…`(폴더/파일 선택 + 최근 항목) 또는 입력칸에 Git URL/경로 입력 후 `＋ 목록에 추가`
2. **분석 ▶ (전체)** — 목록의 항목들을 한 번에 분석 (결과는 프로젝트별 탭으로 누적, 민감정보 있으면 🔴 표시)
3. **결과 확인** — 각 결과의 하위 탭: `요약 / 파일 / 문서 / ✍ 사용자 작성`
   - **문서**: 노란 강조(직접 작성 필요) 줄 우측 `✏ 편집`으로 그 줄만 작성(플레이스홀더·초기화 지원),
     `✏ 문서 직접 수정`으로 전체 편집, `🔎 찾기`로 검색
   - **✍ 사용자 작성**: 작성자/제목/내용 입력 → `추가` 시 문서 상단에 머지(`＋ 입력폼 추가`로 여러 개)
   - `💾 이 결과 저장`(md/html/txt), `📸 스냅샷/비교`(이전 분석 대비 변경), 상태바 `💾 전체 저장`(모든 탭 일괄)

## 분석 대상
**폴더**(프로젝트 전체), **개별 파일**(.java/.py/문서 등), **Git URL**

## 분석 항목
- 기술 구성: 언어별 코드 비중 차트, 파일 형식 분포(표)
- 의존성: `requirements.txt`·`package.json` 상세, `pyproject.toml`·`pom.xml`·`build.gradle`·`go.mod`·`Gemfile`·`Cargo.toml` 항목 파싱
- 준비사항(런타임·설치 명령), 실행 진입점, 포트(추정), 필요 환경변수
- 주요 구성 파일(Docker/CI/설정)·테스트 감지
- **민감정보 의심**: 비밀값·접속문자열·AWS/JWT/Slack/GitHub/Google 키·Bearer·개인키 → 값 마스킹 + 위치·신뢰도
- **단일 코드 파일**: 임포트·클래스·함수·**API 라우트(엔드포인트)**·진입점 추출 + "무엇을 하는 코드인지" 휴리스틱 요약
  (Python/Java/JS/TS/Go/Ruby/C#/Kotlin)

## 문서 양식
- 제목 = 분석대상명 + 작성일, 항목별 **✅ 자동 추출 / ✍ 직접 입력 필요 / ➖ 해당 없음** 구분
- 프로젝트(실행지향 9개 섹션 + 표·차트)와 단일 파일(코드분석 중심)은 서로 다른 양식

## 내보내기 포맷
저장 시 확장자에 따라 자동 변환: `.md`·`.txt`(Markdown 원문), `.html`(보기 좋은 HTML).

## 테스트 / 빌드 / 배포
```bash
python -m unittest discover -s tests          # 테스트
pip install pyinstaller                        # 빌드 전용
python -m PyInstaller --onefile --windowed --name handover-gui --clean --noconfirm handover_gui.py
```
- **CI(GitHub Actions)**: push/PR 시 테스트(3.9·3.12), **버전 태그(`v*`) 푸시 시 Windows exe 자동 빌드·Release 첨부**
- 새 버전 배포: 버전 올리고 `git tag vX.Y.Z && git push origin vX.Y.Z`

## 한계
- 자동 추출은 빗나갈 수 있다. 문서의 `✍ 직접 입력 필요` 항목과 `주의사항`을 반드시 검토할 것.
- 민감정보·코드 분석은 패턴 기반(휴리스틱)이라 오탐·누락이 있을 수 있다. 사람이 최종 확인할 것.
- 파일 드래그&드롭·완전한 다크모드는 외부 라이브러리/대규모 테마 변경이 필요해 미적용(0-의존성 유지).
