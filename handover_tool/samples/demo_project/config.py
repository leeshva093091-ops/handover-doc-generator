"""데모용 설정 파일 — 민감정보 탐지 테스트를 위한 '가짜' 값이 들어 있다.

주의: 아래 값은 전부 실제와 무관한 테스트용 더미다 (도구가 잘 잡는지 확인용).
"""

import os

# 하드코딩된 비밀번호 (탐지 대상, 가짜 값)
DB_PASSWORD = "s3cr3tP@ssw0rd"

# 자격증명을 포함한 접속 문자열 (탐지 대상, 가짜 값)
DATABASE_URL = "postgresql://admin:p4ssw0rd@db.internal:5432/demo"

# 환경변수로 주입받는 값 (필요 환경변수로 수집되어야 함)
API_KEY = os.getenv("DEMO_API_KEY")
SECRET_TOKEN = os.environ.get("DEMO_SECRET_TOKEN")
