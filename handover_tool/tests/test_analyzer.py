"""분석기 기본 동작 테스트 (표준 라이브러리 unittest — 추가 패키지 불필요).

실행: python -m unittest discover -s tests   (handover_tool 디렉터리에서)
"""

import json
import sys
import unittest
from pathlib import Path

# tests/ 에서 바로 실행해도 handover 패키지를 찾도록 루트를 경로에 추가.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handover.analyzer import analyze_project  # noqa: E402
from handover.template import render_markdown  # noqa: E402
from handover import secrets  # noqa: E402
from handover import source  # noqa: E402
from handover import web  # noqa: E402
from handover import snapshot  # noqa: E402
from handover.service import generate_document  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "samples" / "demo_project"


class AnalyzeSampleTest(unittest.TestCase):
    def setUp(self):
        self.meta = analyze_project(SAMPLE)

    def test_detects_python(self):
        self.assertIn("Python", self.meta.languages)

    def test_parses_requirements(self):
        sources = [g.source for g in self.meta.dependencies]
        self.assertIn("requirements.txt", sources)
        flask_listed = any("flask" in item for g in self.meta.dependencies for item in g.items)
        self.assertTrue(flask_listed)

    def test_finds_entrypoint(self):
        details = " ".join(e.detail for e in self.meta.run_entries)
        self.assertIn("app.py", details)

    def test_finds_port(self):
        self.assertIn("8080", self.meta.ports)

    def test_readme_excerpt(self):
        self.assertIsNotNone(self.meta.readme_excerpt)

    def test_files_listed(self):
        self.assertIn("app.py", self.meta.files)
        self.assertIn("config.py", self.meta.files)
        self.assertIn("requirements.txt", self.meta.files)
        self.assertGreaterEqual(len(self.meta.files), 4)

    def test_prerequisites_derived(self):
        prereq = " | ".join(self.meta.prerequisites)
        self.assertIn("Python 런타임", prereq)
        self.assertIn("pip install -r requirements.txt", prereq)
        self.assertIn("환경변수", prereq)          # DEMO_API_KEY 등
        self.assertIn("접속 정보", prereq)          # 접속 문자열 감지 → 준비사항

    def test_prerequisites_rendered(self):
        doc = render_markdown(self.meta)
        self.assertIn("### 준비사항(Prerequisites)", doc)

    def test_title_is_name_and_date(self):
        doc = render_markdown(self.meta, generated_on="2026-06-17")
        self.assertTrue(doc.startswith("# demo_project"))
        self.assertIn("작성일 2026-06-17", doc)
        self.assertNotIn("인수인계 문서 —", doc)

    def test_render_has_fixed_sections(self):
        doc = render_markdown(self.meta)
        for heading in ("## 1. 개요", "## 2. 실행 준비", "## 3. 환경 설정",
                        "## 4. 실행 방법", "## 5. 동작 확인", "## 6. 주의사항",
                        "## 7. 디렉터리 구조"):
            self.assertIn(heading, doc)

    def test_tristate_markers(self):
        doc = render_markdown(self.meta)
        # 동작 확인은 항상 직접 작성 필요 표식이 있어야 한다
        self.assertIn("✍", doc)
        self.assertIn("➖", doc)  # 해당 없음 표식도 존재

    def test_detects_sensitive(self):
        kinds = [f.kind for f in self.meta.sensitive]
        # 하드코딩 비밀값과 접속 문자열 모두 잡혀야 한다.
        self.assertTrue(any("비밀값" in k for k in kinds), kinds)
        self.assertTrue(any("접속 문자열" in k for k in kinds), kinds)

    def test_sensitive_values_are_masked(self):
        # 원본 비밀값/비밀번호가 그대로 노출되면 안 된다.
        doc = render_markdown(self.meta)
        self.assertNotIn("s3cr3tP@ssw0rd", doc)
        self.assertNotIn("p4ssw0rd", doc)

    def test_collects_env_vars(self):
        self.assertIn("DEMO_API_KEY", self.meta.env_vars)
        self.assertIn("DEMO_SECRET_TOKEN", self.meta.env_vars)


class SecretsUnitTest(unittest.TestCase):
    def test_placeholder_lowers_confidence(self):
        findings = secrets.scan_text("x.py", 'password = "changeme"')
        self.assertTrue(findings)
        self.assertEqual(findings[0].confidence, "낮음")

    def test_mask_hides_value(self):
        masked = secrets.mask("supersecret")
        self.assertNotEqual(masked, "supersecret")
        self.assertIn("*", masked)

    def test_env_var_not_flagged_as_hardcoded(self):
        # os.getenv 참조는 하드코딩 비밀이 아니므로 민감정보로 잡지 않아야 한다.
        findings = secrets.scan_text("x.py", 'api_key = os.getenv("API_KEY")')
        self.assertEqual(findings, [])


class MissingPathTest(unittest.TestCase):
    def test_empty_dir_does_not_crash(self):
        # 빈 폴더여도 예외 없이 'notes'에 안내가 채워져야 한다 (엣지 케이스).
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            meta = analyze_project(Path(tmp))
            self.assertTrue(meta.notes)  # 확인 필요 안내가 있어야 함
            render_markdown(meta)  # 렌더링도 깨지지 않아야 함


class SourceTest(unittest.TestCase):
    def test_is_url(self):
        for url in ("https://github.com/o/r.git", "git@github.com:o/r.git",
                    "ssh://git@host/o/r", "http://internal/o/r.git"):
            self.assertTrue(source.is_url(url), url)
        for local in ("./samples", "C:\\proj", "/home/u/proj", "samples/demo_project"):
            self.assertFalse(source.is_url(local), local)

    def test_repo_name_from_url(self):
        self.assertEqual(source.repo_name_from_url("https://github.com/octocat/Hello-World.git"),
                         "Hello-World")
        self.assertEqual(source.repo_name_from_url("git@github.com:owner/my-repo.git"), "my-repo")
        self.assertEqual(source.repo_name_from_url("https://host/owner/proj/"), "proj")

    def test_resolve_local_ok(self):
        resolved = source.resolve(str(SAMPLE))
        try:
            self.assertEqual(resolved.path, SAMPLE)
            self.assertEqual(resolved.name, "demo_project")
        finally:
            resolved.cleanup()

    def test_resolve_local_missing_raises(self):
        with self.assertRaises(source.SourceError):
            source.resolve(str(SAMPLE.parent / "없는경로_xyz"))


class WebTest(unittest.TestCase):
    def test_form_renders(self):
        page = web.render_form()
        self.assertIn("<form", page)
        self.assertIn("name='source'", page)

    def test_form_escapes_error_and_value(self):
        # 사용자 입력/에러 메시지는 이스케이프되어 XSS로 이어지지 않아야 한다.
        page = web.render_form(error="<script>x</script>", value="<b>v</b>")
        self.assertNotIn("<script>x</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_result_has_document_and_download(self):
        document, meta = generate_document(str(SAMPLE))
        page = web.render_result(str(SAMPLE), document, meta)
        self.assertIn("<textarea", page)
        self.assertIn("download=", page)
        # 샘플엔 민감정보가 있으므로 경고가 떠야 한다.
        self.assertIn("민감정보 의심", page)
        # 마스킹된 값만 노출되고 원본 비밀번호는 페이지에 없어야 한다.
        self.assertNotIn("s3cr3tP@ssw0rd", page)


class ServiceTest(unittest.TestCase):
    def test_generate_document_local(self):
        document, meta = generate_document(str(SAMPLE))
        self.assertIn("## 1. 개요", document)
        self.assertEqual(meta.name, "demo_project")


class SingleFileTest(unittest.TestCase):
    def test_analyze_single_file(self):
        # 폴더가 아닌 개별 파일도 분석 가능해야 한다 (config.py에 가짜 비밀값 포함).
        doc, meta = generate_document(str(SAMPLE / "config.py"))
        self.assertEqual(meta.name, "config.py")
        self.assertEqual(meta.kind, "file")
        self.assertEqual(meta.files, ["config.py"])
        self.assertIn("Python", meta.languages)
        self.assertTrue(meta.sensitive)  # 하드코딩 비밀값 감지

    def test_file_template_differs_from_project(self):
        # 단일 파일은 코드 분석 섹션을 포함하고, 프로젝트 전용 섹션은 없어야 한다.
        doc, meta = generate_document(str(SAMPLE / "app.py"))
        self.assertTrue(doc.startswith("# app.py"))      # 제목 = 파일명
        self.assertIn("## 2. 코드 분석", doc)
        self.assertNotIn("디렉터리 구조", doc)             # 프로젝트 전용 섹션 없음

    def test_code_insight_python(self):
        _, meta = generate_document(str(SAMPLE / "app.py"))
        self.assertIsNotNone(meta.code)
        self.assertEqual(meta.code.language, "Python")
        self.assertIn("main", meta.code.functions)   # def main() 존재
        self.assertTrue(meta.code.has_entrypoint)     # __main__ 가드 존재
        self.assertTrue(meta.code.summary)

    def test_single_text_file(self):
        doc, meta = generate_document(str(SAMPLE / "README.md"))
        self.assertEqual(meta.name, "README.md")
        self.assertIsNotNone(meta.readme_excerpt)  # 내용 미리보기


class ExportTest(unittest.TestCase):
    def setUp(self):
        from handover import export
        self.export = export
        self.doc, self.meta = generate_document(str(SAMPLE))

    def test_html_has_structure(self):
        out = self.export.to_html(self.doc, "테스트")
        self.assertIn("<!doctype html>", out)
        self.assertIn("<h1>", out)
        self.assertIn("<h2>", out)
        self.assertIn("<table>", out)  # 민감정보 표 → HTML 표
        self.assertIn("<title>테스트</title>", out)

    def test_html_escapes(self):
        out = self.export.to_html("# <script>x</script>", "t")
        self.assertNotIn("<script>x</script>", out)

    def test_render_by_ext(self):
        self.assertEqual(self.export.render(self.doc, ".md"), self.doc)
        self.assertEqual(self.export.render(self.doc, ".txt"), self.doc)
        self.assertIn("<html", self.export.render(self.doc, ".html"))


class SnapshotDiffTest(unittest.TestCase):
    def setUp(self):
        _, self.meta = generate_document(str(SAMPLE))
        self.snap = snapshot.to_snapshot(self.meta)

    def test_no_change_is_empty(self):
        d = snapshot.diff(self.snap, self.snap)
        self.assertTrue(d.is_empty())
        self.assertIn("변경된 항목이 없습니다", snapshot.render_diff_md(d))

    def test_added_dependency_detected(self):
        old = json.loads(json.dumps(self.snap))  # 깊은 복사
        old["dependencies"] = [x for x in old["dependencies"] if "flask" not in x]
        d = snapshot.diff(old, self.snap)
        added, _ = d.changes["의존성"]
        self.assertTrue(any("flask" in x for x in added))

    def test_new_sensitive_flagged(self):
        old = json.loads(json.dumps(self.snap))
        old["sensitive"] = []  # 이전엔 민감정보가 없었다고 가정
        d = snapshot.diff(old, self.snap)
        self.assertTrue(d.has_new_sensitive())
        md = snapshot.render_diff_md(d)
        self.assertIn("새로 발견된 민감정보", md)

    def test_save_load_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "snap.json"
            snapshot.save(p, self.snap)
            loaded = snapshot.load(p)
            self.assertEqual(loaded["name"], self.snap["name"])

    def test_missing_snapshot_returns_none(self):
        self.assertIsNone(snapshot.load(Path("이런파일_없음_zzz.json")))

    def test_render_with_diff_adds_section(self):
        d = snapshot.diff({"env_vars": []}, {"env_vars": ["NEW_VAR"]})
        doc = render_markdown(self.meta, diff_md=snapshot.render_diff_md(d))
        self.assertIn("## 변경 사항 (이전 분석 대비)", doc)
        self.assertIn("NEW_VAR", doc)


if __name__ == "__main__":
    unittest.main()
