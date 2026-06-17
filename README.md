# 인수인계 문서 자동 생성기

프로젝트 폴더·개별 파일·Git URL을 넣으면 **설치·실행·주의사항**을 정형 문서로 만들어 주는
**데스크톱 GUI 프로그램**입니다. 분석·UI 모두 **파이썬 표준 라이브러리만** 사용합니다(외부 패키지 0).

- 자동 분석: 언어/구성, 의존성·준비사항, 실행 방법, 환경변수, 포트
- 민감정보(비밀값·접속정보·키) 자동 탐지 + 마스킹
- 단일 코드 파일은 "무엇을 하는 코드인지" 구조·요약 분석
- 표·차트가 포함된 상세 문서, 직접 작성 필요 항목 표시·인라인 편집
- Markdown / HTML / 텍스트로 내보내기

## 바로 실행 (Windows, 권장)
1. **[Releases](https://github.com/leeshva093091-ops/handover-doc-generator/releases)** 에서 `handover-gui.exe` 다운로드
2. **더블클릭** 실행 — Python 설치 불필요(인터프리터·tkinter 내장)
3. `프로젝트 찾아보기…`로 폴더/파일 선택 또는 Git URL 입력 → `분석 ▶`

> Git URL 분석만 실행 PC에 `git` 필요(폴더/파일 분석은 불필요). 창 우측 상단에서 Git 사용 가능 여부 확인.

## 소스로 실행 (Windows / macOS / Linux)
```bash
git clone https://github.com/leeshva093091-ops/handover-doc-generator.git
cd handover-doc-generator/handover_tool
python handover_gui.py          # handover_tool 폴더 안에서 실행
```
- **요구사항**: Python 3.9+ (표준 라이브러리만). 추가 패키지 설치 불필요.
- **tkinter**: Windows/macOS python.org 설치본엔 포함. **Linux는** `sudo apt install python3-tk` 필요.
- 테스트: `python -m unittest discover -s tests`

## 직접 exe 빌드
```bash
cd handover_tool
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name handover-gui --clean --noconfirm handover_gui.py
# → dist/handover-gui.exe
```

## 문서
- 상세 사용법: [handover_tool/README.md](handover_tool/README.md)
- 설치 가이드(온라인/오프라인): [handover_tool/INSTALL.md](handover_tool/INSTALL.md)
- 기획/진행: [PRD.md](PRD.md) · [CHECKLIST.md](CHECKLIST.md)

## 한계
자동 추출은 빗나갈 수 있습니다. 문서의 `✍ 직접 입력 필요` 항목과 `주의사항`을 반드시 검토하세요.
민감정보·코드 분석은 패턴 기반(휴리스틱)이라 오탐·누락이 있을 수 있습니다.
