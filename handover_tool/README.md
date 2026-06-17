# 인수인계 문서 자동 생성기 (GUI)

![version](https://img.shields.io/badge/version-0.4.0-blue.svg)
![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![dependencies](https://img.shields.io/badge/dependencies-none%20(stdlib)-brightgreen.svg)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

프로젝트 폴더·개별 파일·Git URL을 넣으면 **설치·실행·주의사항**을 정형 문서로 뽑아주는
**데스크톱 GUI 프로그램**. UI(tkinter)와 분석 모두 **외부 패키지 없이 파이썬 표준 라이브러리만** 사용한다.

> **저장소**: https://github.com/leeshva093091-ops/handover-doc-generator
> 기획 배경/범위: 상위 폴더의 [PRD.md](../PRD.md), 진행 현황: [CHECKLIST.md](../CHECKLIST.md)

## 요구사항
- Python 3.9 이상 (표준 라이브러리만 사용, 추가 설치 불필요)
- (선택) `git` — **Git URL 입력**을 쓸 때만 필요. 폴더/파일 분석에는 불필요.

## 실행
```bash
# 개발 중 실행 (handover_tool 디렉터리에서)
python handover_gui.py
```
배포본은 아래 빌드한 **`handover-gui.exe`를 더블클릭**하면 된다 (Python 설치 불필요).

## 사용 흐름 (GUI)
1. **프로젝트 추가** — `프로젝트 찾아보기…`(폴더/파일 선택 메뉴) 또는 입력칸에 Git URL/경로 입력 후 `＋ 목록에 추가`
2. **분석 ▶ (전체)** — 목록의 항목들을 한 번에 분석 (결과는 프로젝트별 탭으로 누적)
3. **결과 확인** — 각 탭의 `요약 / 파일 / 문서` 하위 탭
   - 문서의 노란 강조(직접 작성 필요) 줄 우측 `✏ 편집` 버튼으로 그 줄만 작성
   - `✏ 문서 직접 수정`으로 전체 편집, `💾 이 결과 저장`으로 내보내기

## 분석 대상
- **폴더**(프로젝트 전체), **개별 파일**(.java/.py/문서 등), **Git URL**

## 분석 항목
- 주요 언어(확장자 빈도), README/주석 기반 설명
- 의존성(`requirements.txt`·`package.json` 등), 준비사항(런타임·설치 명령)
- 실행 진입점, 포트(추정), 필요 환경변수(`os.getenv`/`process.env` 등)
- **민감정보 의심**: 하드코딩 비밀값·접속문자열·AWS 키·Bearer 토큰·개인키 → 값 마스킹 + 위치·신뢰도
- 디렉터리 구조 + 대상 파일 목록(확장자 분포)
- **단일 코드 파일**: 임포트·클래스·함수·진입점 추출 + "무엇을 하는 코드인지" 휴리스틱 요약

## 문서 양식
- 제목 = 분석대상명 + 작성일, 항목별 **✅ 자동 추출 / ✍ 직접 입력 필요 / ➖ 해당 없음** 구분
- 프로젝트와 단일 파일은 서로 다른 양식 (프로젝트: 실행지향 / 파일: 코드분석 중심)

## 내보내기 포맷
저장 시 확장자에 따라 자동 변환: `.md`·`.txt`(Markdown 원문), `.html`(보기 좋은 HTML로 변환).

## 테스트
```bash
python -m unittest discover -s tests
```

## 단독 실행 파일(.exe) 빌드 — 배포용
배포 PC에 **Python 설치 없이** 실행할 수 있는 GUI 단일 exe를 만든다.
빌드는 인터넷 되는 PC에서 한 번만 하고, 결과 `dist\handover-gui.exe`만 옮기면 된다.

```bash
pip install pyinstaller          # 빌드 전용 도구 (런타임 의존성 아님)
python -m PyInstaller --onefile --windowed --name handover-gui --clean --noconfirm handover_gui.py
# → dist\handover-gui.exe (약 10MB)
```
> - **폴더·파일 분석**은 exe 단독으로 완전히 동작한다.
> - **Git URL** 입력만은 실행 PC에 `git`이 설치돼 있어야 한다.
> - onefile exe는 백신이 오탐할 수 있으니, 사내 배포 전 보안 정책을 확인할 것.

## 한계
- 자동 추출은 빗나갈 수 있다. 문서의 `✍ 직접 입력 필요` 항목과 `주의사항`을 반드시 검토할 것.
- 민감정보·코드 분석은 패턴 기반(휴리스틱)이라 오탐·누락이 있을 수 있다. 사람이 최종 확인할 것.
