"""PyInstaller 빌드용 진입 스크립트 (handover.exe 엔트리포인트).

`python -m handover`와 동일하게 동작한다. PyInstaller는 이 스크립트에서 시작해 import를
따라가며 handover 패키지 전체(web/source/snapshot 등)를 번들에 포함한다.
"""

import sys

from handover.cli import main

if __name__ == "__main__":
    sys.exit(main())
