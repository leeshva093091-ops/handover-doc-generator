# 설치 가이드 — Python & 인수인계 도구

이 도구는 **파이썬 표준 라이브러리만** 사용하므로, Python만 설치하면 추가 패키지 없이 바로 실행된다.
환경에 따라 **온라인(인터넷 가능)** / **오프라인(사내 폐쇄망)** 두 경로로 나눠 안내한다.

- 요구사항: **Python 3.9 이상** (권장: 3.11~3.13 최신 안정 버전)
- 대상 OS: Windows (다른 OS는 맨 아래 참고)

---

## A. 온라인 환경 (인터넷 가능)

### A-1. winget 사용 (가장 간단, 권장)
```powershell
winget install --id Python.Python.3.13 -e --scope user --silent --accept-source-agreements --accept-package-agreements
```
- `--scope user`: 관리자 권한(UAC) 없이 현재 사용자에 설치.
- 설치 후 **새 터미널**을 열어야 PATH가 반영된다.

### A-2. 공식 설치 파일 사용
1. <https://www.python.org/downloads/windows> 접속
2. **"Windows installer (64-bit)"** `.exe` 다운로드
3. 실행 → ✅ **"Add python.exe to PATH"** 체크 → Install Now

---

## B. 오프라인 / 사내 폐쇄망 환경

핵심 원칙: **인터넷 되는 PC에서 설치 파일을 받아 → 사내 반입 절차로 폐쇄망 PC에 옮긴다.**

### B-1. 받을 파일 (인터넷 PC에서)
<https://www.python.org/downloads/windows> 에서 받는다.

| 파일 | 오프라인 사용 | 비고 |
|---|---|---|
| **Windows installer (64-bit)** `.exe` | ✅ 권장 | 인터넷 없이 설치 가능 |
| Windows **embeddable** package `.zip` | ✅ 대안 | 설치 권한이 없을 때 (B-3) |
| Web-based installer | ❌ 불가 | 설치 중 인터넷 필요 |

> ⚠️ "Web-based installer"는 폐쇄망에서 동작하지 않는다. 반드시 위의 정식 `.exe`(또는 embeddable zip)를 받을 것.

### B-2. 정식 설치 (설치 권한이 있을 때)
1. 반입한 `.exe` 실행
2. ✅ **"Add python.exe to PATH"** 체크 (안 하면 `python` 명령이 안 잡힘)
3. Install Now → 완료 후 **새 터미널**에서 확인

### B-3. 무설치(embeddable) 방식 (설치 권한이 없을 때)
1. `python-3.x.x-embed-amd64.zip` 을 원하는 폴더에 압축 해제 (예: `C:\tools\python`)
2. 해당 폴더의 `python.exe` 를 직접 호출하거나, 그 폴더를 PATH에 추가
3. 표준 라이브러리만 쓰는 이 도구는 embeddable 런타임으로도 동작한다.
   (단, embeddable에는 pip가 기본 포함되지 않으므로 외부 패키지가 필요해지면 별도 작업 필요 → 현재 MVP는 불필요)

### B-4. (참고) 외부 패키지가 필요해질 때 — 2단계 웹 화면 이후
MVP는 표준 라이브러리만 쓰지만, 웹 화면 단계에서 Flask 등을 도입하면 폐쇄망에 패키지를 반입해야 한다.
인터넷 PC에서 `.whl`을 미리 받아 옮긴 뒤 오프라인 설치:
```powershell
# 인터넷 PC: 의존성 휠 파일 모으기
pip download flask -d .\wheels
# 폐쇄망 PC: 받은 휠로만 설치 (인덱스 미접속)
pip install --no-index --find-links=.\wheels flask
```

---

## C. 공통 — 설치 후 처리

### C-1. Windows 스토어 alias 끄기 (자주 겪는 함정)
`python` 입력 시 Microsoft Store로 튄다면, alias 스텁이 가로채는 것이다.
- **설정 → 앱 → 고급 앱 설정 → 앱 실행 별칭** → `python.exe` / `python3.exe` **끄기**

### C-2. 설치 검증
```powershell
python --version        # 예: Python 3.13.14
```

---

## D. 도구 실행 & 검증

```powershell
cd C:\lshDEV\itcen_edu_0617\handover_tool

# 단위 테스트 (표준 라이브러리 unittest — 추가 설치 불필요)
python -m unittest discover -s tests

# 샘플 프로젝트 분석 (결과 미리보기)
python -m handover .\samples\demo_project

# 파일로 저장
python -m handover .\samples\demo_project -o handover.md
```

테스트가 모두 통과하고 6섹션 인수인계 문서가 출력되면 정상이다.

---

## 참고
- macOS/Linux: 보통 Python이 기본 포함되거나 패키지 매니저(`brew`, `apt` 등)로 설치. 명령은 `python3` 사용.
- 사내 보안 정책상 외부 파일 반입·실행에 승인이 필요할 수 있으니 정식 절차를 먼저 확인할 것.
