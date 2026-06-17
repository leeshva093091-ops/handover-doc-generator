# 인수인계 문서 자동 생성기 (MVP)

프로젝트 폴더를 넣으면 **설치·실행·주의사항**을 항상 같은 양식의 Markdown 인수인계
문서로 뽑아준다. 폐쇄망 제약을 고려해 **외부 패키지 없이 파이썬 표준 라이브러리만** 사용한다.

> 기획 배경/범위: 상위 폴더의 [PRD.md](../PRD.md), 진행 현황: [CHECKLIST.md](../CHECKLIST.md)

## 요구사항
- Python 3.9 이상 (표준 라이브러리만 사용, 추가 설치 불필요)
- (선택) `git` — **Git URL 입력**을 쓸 때만 필요. 로컬 폴더 분석에는 불필요.

## 사용법
```bash
# handover_tool 디렉터리에서 실행
python -m handover ./samples/demo_project              # 로컬 폴더 미리보기
python -m handover ./samples/demo_project -o out.md    # 파일로 저장
python -m handover https://github.com/owner/repo.git   # Git URL (임시 클론 후 분석)
python -m handover --serve                             # 웹 화면 (기본 http://127.0.0.1:8765)
python -m handover --serve --port 9000                 # 포트 변경
python -m handover ./my-project --snapshot ./my.snap   # 재분석 diff (이전 대비 변경 사항)
python -m handover --version
```

### 재분석 diff (`--snapshot`)
같은 프로젝트를 주기적으로 갱신할 때, 이전 분석 대비 무엇이 바뀌었는지 보여준다.
```bash
python -m handover ./proj --snapshot ./proj.snap -o handover.md   # 1회차: 스냅샷 생성
# ... 코드 변경 후 ...
python -m handover ./proj --snapshot ./proj.snap -o handover.md   # 2회차: '7. 변경 사항' 섹션 추가
```
- 의존성·환경변수·실행방법·포트·민감정보의 **추가/제거**를 표시한다.
- **새로 생긴 민감정보**는 별도 경고로 강조한다.
- 스냅샷 파일은 실행할 때마다 최신 상태로 갱신된다.
> Git URL은 `git clone --depth 1`로 임시 디렉터리에 받아 분석하고, 끝나면 자동 정리한다.
> 폐쇄망 내부 GitHub(Enterprise)도 git 접근이 되면 동일하게 동작한다. git이 없으면
> 저장소를 직접 클론한 뒤 로컬 경로로 넘기면 된다.

## 분석 항목
- 주요 언어 (확장자 빈도)
- README 발췌 → 개요
- 의존성: `requirements.txt`, `package.json`(상세) / 그 외 파일은 존재 여부 표시
- 실행 방법: 진입점(`main.py`/`app.py`/`manage.py` 등), 셸 스크립트, Makefile, Docker, npm scripts
- 포트(추정) — 오탐 가능, 문서의 '주의사항'에서 검증 유도
- **필요 환경변수**: `os.getenv`/`os.environ`/`process.env`/`System.getenv` 참조 수집
- **민감정보 의심**: 하드코딩된 비밀값·자격증명 접속문자열·AWS 키·Bearer 토큰·개인키 탐지
  → 값은 **마스킹**, 위치(`파일:줄`)·신뢰도(높음/중간/낮음)와 함께 '주의사항' 표로 출력
- 디렉터리 구조 (상위 2단계)

## 테스트
```bash
python -m unittest discover -s tests
```

## 단독 실행 파일(.exe) 빌드 — 폐쇄망 배포용
배포받는 PC에 **Python 설치 없이** 실행할 수 있는 단일 exe를 만든다.
빌드는 인터넷 되는 빌드 PC에서 한 번만 하고, 결과 `dist\handover.exe`만 폐쇄망으로 반입한다.

```bash
# 빌드 PC (인터넷 필요)
pip install pyinstaller          # 빌드 전용 도구 (런타임 의존성 아님)
python -m PyInstaller --onefile --name handover --clean --noconfirm handover_cli.py
# → dist\handover.exe (약 7~8MB) 생성
```

배포 후 사용 (대상 PC, Python 불필요):
```bat
handover.exe .\my-project -o handover.md     :: 로컬 폴더 분석
handover.exe --serve                          :: 웹 화면 (http://127.0.0.1:8765)
handover.exe https://github.com/owner/repo.git :: Git URL (단, 대상 PC에 git 필요)
```

> - **로컬 폴더 분석·웹 모드**는 exe 단독으로 완전히 동작한다.
> - **Git URL** 입력만은 실행 PC에 `git`이 설치돼 있어야 한다 (exe가 git을 포함하지 않음).
> - onefile exe는 백신이 오탐할 수 있으니, 사내 배포 전 보안 정책을 확인할 것.

## 현재 단계와 한계
- **1단계(MVP)** + **2단계 전체**(민감정보/환경변수, 웹 화면, Git URL) + **3단계 재분석 diff** 완료.
- 웹 서버는 보안상 기본 `127.0.0.1`(로컬 전용) 바인드. 외부 노출은 권장하지 않음.
- 남은 것: 3단계 일부(다언어 확장, HTML 등 내보내기 포맷 확장).
- 자동 추출은 빗나갈 수 있다. 생성 문서의 `확인 필요`/`주의사항`을 반드시 검토할 것.
- 민감정보 탐지는 패턴 기반이라 **오탐·누락이 있을 수 있다.** 신뢰도와 무관하게 사람이 최종 확인할 것.
