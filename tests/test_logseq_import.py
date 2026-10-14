from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY_ROOT / "scripts" / "post_workflow.py"


class LogseqImportTests(unittest.TestCase):
    def run_command(
        self, *arguments: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(arguments),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )

    def create_logseq_clone(self, root: Path) -> Path:
        remote = root / "logseq-remote.git"
        seed = root / "logseq-seed"
        clone = root / "logseq-clone"
        self.assertEqual(0, self.run_command("git", "init", "--bare", str(remote)).returncode)
        self.assertEqual(0, self.run_command("git", "init", "-b", "master", str(seed)).returncode)
        self.assertEqual(
            0,
            self.run_command(
                "git", "config", "user.name", "Workflow Test", cwd=seed
            ).returncode,
        )
        self.assertEqual(
            0,
            self.run_command(
                "git", "config", "user.email", "workflow@example.invalid", cwd=seed
            ).returncode,
        )

        page = seed / "pages" / "Blog___测试文章.md"
        page.parent.mkdir(parents=True)
        page.write_text(
            "- {{renderer :smartblock, article_blog, New Smartblock, false}}\n"
            "\t- class:: article\n"
            "\t  alias::\n"
            "\t  tags:: #[[zzz-📤outbox 费曼输出/文章输出]]\n"
            "\t  blog-tags:: AI, Agent\n"
            "\t  created:: [[2026-10-14]]\n"
            "\t  slug:: blog-from-logseq-test\n"
            "\t  public:: false\n"
            "\t  status:: writing\n"
            "\t- ## 摘要\n"
            "\t\t- 这是摘要\n"
            "\t- ## 正文\n"
            "\t\t- 这是正文\n"
            "\t\t- ![测试图片](../assets/image_123.png)\n"
            "\t- ## ref.\n"
            "\t\t- 参考资料\n",
            encoding="utf-8",
        )
        asset = seed / "assets" / "image_123.png"
        asset.parent.mkdir()
        Image.new("RGB", (16, 8), "blue").save(asset)
        self.assertEqual(0, self.run_command("git", "add", ".", cwd=seed).returncode)
        self.assertEqual(
            0,
            self.run_command("git", "commit", "-m", "add article", cwd=seed).returncode,
        )
        self.assertEqual(
            0,
            self.run_command(
                "git", "remote", "add", "origin", str(remote), cwd=seed
            ).returncode,
        )
        self.assertEqual(
            0,
            self.run_command(
                "git", "push", "-u", "origin", "master", cwd=seed
            ).returncode,
        )
        self.assertEqual(0, self.run_command("git", "clone", str(remote), str(clone)).returncode)
        return clone

    def push_logseq_update(self, root: Path, old: str, new: str) -> None:
        seed = root / "logseq-seed"
        page = seed / "pages" / "Blog___测试文章.md"
        page.write_text(
            page.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        self.assertEqual(0, self.run_command("git", "add", str(page), cwd=seed).returncode)
        self.assertEqual(
            0,
            self.run_command(
                "git", "commit", "-m", "update article", cwd=seed
            ).returncode,
        )
        self.assertEqual(0, self.run_command("git", "push", cwd=seed).returncode)

    def push_logseq_page(self, root: Path, filename: str, content: str) -> None:
        seed = root / "logseq-seed"
        page = seed / "pages" / filename
        page.write_text(content, encoding="utf-8")
        self.assertEqual(0, self.run_command("git", "add", str(page), cwd=seed).returncode)
        self.assertEqual(
            0,
            self.run_command("git", "commit", "-m", "add another article", cwd=seed).returncode,
        )
        self.assertEqual(0, self.run_command("git", "push", cwd=seed).returncode)

    def run_workflow(
        self, site: Path, *arguments: str, expected_returncode: int = 0
    ) -> dict[str, object]:
        completed = self.run_command(
            sys.executable,
            str(WORKFLOW),
            "--root",
            str(site),
            *arguments,
        )
        self.assertEqual(
            expected_returncode,
            completed.returncode,
            completed.stderr or completed.stdout,
        )
        return json.loads(completed.stdout)

    def test_imports_a_smartblock_article_and_its_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)

            result = self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
            )

            draft = site / "drafts" / "2026-10-14-blog-from-logseq-test"
            article = draft / "article.md"
            copied_image = draft / "images" / "original" / "image_123.png"
            self.assertEqual("imported", result["status"])
            self.assertEqual("blog-from-logseq-test", result["slug"])
            self.assertEqual(
                "drafts/2026-10-14-blog-from-logseq-test/article.md",
                result["article"],
            )
            self.assertTrue(article.is_file())
            self.assertTrue(copied_image.is_file())
            content = article.read_text(encoding="utf-8")
            self.assertIn("date: 2026-10-14", content)
            self.assertIn("slug: blog-from-logseq-test", content)
            self.assertIn("# 测试文章", content)
            self.assertIn("这是摘要\n\n<!-- more -->", content)
            self.assertIn("这是正文", content)
            self.assertIn("![测试图片](images/original/image_123.png)", content)
            self.assertIn("## 参考资料", content)
            self.assertEqual(1, content.count("<!-- more -->"))

    def test_queue_discovers_ready_article_and_public_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.push_logseq_update(root, "status:: writing", "status:: ready-to-publish")

            result = self.run_workflow(
                site,
                "queue-logseq",
                "--logseq-root",
                str(logseq),
            )

            self.assertEqual("queue", result["status"])
            self.assertEqual(
                [
                    {
                        "slug": "blog-from-logseq-test",
                        "created": "2026-10-14",
                        "blog_tags": ["AI", "Agent"],
                        "source": "pages/Blog___测试文章.md",
                    }
                ],
                result["articles"],
            )

    def test_queue_treats_no_ready_articles_as_normal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)

            result = self.run_workflow(
                site,
                "queue-logseq",
                "--logseq-root",
                str(logseq),
            )

            self.assertEqual("queue", result["status"])
            self.assertEqual([], result["articles"])

    def test_queue_blocks_ready_article_with_missing_required_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.push_logseq_update(root, "status:: writing", "status:: ready-to-publish")
            self.push_logseq_update(root, "blog-tags:: AI, Agent", "blog-tags::")

            result = self.run_workflow(
                site,
                "queue-logseq",
                "--logseq-root",
                str(logseq),
                expected_returncode=2,
            )

            error = "\n".join(result["errors"])
            self.assertIn("pages/Blog___测试文章.md", error)
            self.assertIn("blog-tags", error)

    def test_queue_blocks_duplicate_ready_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.push_logseq_update(root, "status:: writing", "status:: ready-to-publish")
            self.push_logseq_page(
                root,
                "Blog___重复文章.md",
                "- class:: article\n"
                "  blog-tags:: AI\n"
                "  created:: [[2026-10-15]]\n"
                "  slug:: blog-from-logseq-test\n"
                "  status:: ready-to-publish\n",
            )

            result = self.run_workflow(
                site,
                "queue-logseq",
                "--logseq-root",
                str(logseq),
                expected_returncode=2,
            )

            error = "\n".join(result["errors"])
            self.assertIn("重复 slug blog-from-logseq-test", error)
            self.assertIn("Blog___测试文章.md", error)
            self.assertIn("Blog___重复文章.md", error)

    def test_queue_blocks_an_invalid_creation_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.push_logseq_update(root, "status:: writing", "status:: ready-to-publish")
            self.push_logseq_update(root, "created:: [[2026-10-14]]", "created:: someday")

            result = self.run_workflow(
                site,
                "queue-logseq",
                "--logseq-root",
                str(logseq),
                expected_returncode=2,
            )

            error = "\n".join(result["errors"])
            self.assertIn("Blog___测试文章.md", error)
            self.assertIn("created", error)
            self.assertIn("YYYY-MM-DD", error)

    def test_imported_draft_is_resolved_by_public_slug_for_status_and_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
            )

            status = self.run_workflow(site, "status", "blog-from-logseq-test")
            checked = self.run_workflow(site, "check", "blog-from-logseq-test")

            self.assertEqual("draft", status["status"])
            self.assertEqual("checked", checked["status"])
            self.assertEqual([], checked["errors"])

    def test_import_uses_blog_tags_without_leaking_internal_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)

            result = self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
            )

            self.assertEqual("imported", result["status"])
            article = (
                site
                / "drafts"
                / "2026-10-14-blog-from-logseq-test"
                / "article.md"
            ).read_text(encoding="utf-8")
            self.assertIn("  - AI", article)
            self.assertIn("  - Agent", article)
            self.assertNotIn("zzz-📤outbox", article)

    def test_reimport_refreshes_an_unchanged_generated_draft_from_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            arguments = (
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
            )
            self.run_workflow(site, *arguments)
            self.run_workflow(site, "check", "blog-from-logseq-test")
            self.push_logseq_update(root, "这是正文", "这是更新后的正文")

            result = self.run_workflow(site, *arguments)
            status = self.run_workflow(site, "status", "blog-from-logseq-test")

            article = (
                site
                / "drafts"
                / "2026-10-14-blog-from-logseq-test"
                / "article.md"
            )
            self.assertEqual("imported", result["status"])
            self.assertIn("这是更新后的正文", article.read_text(encoding="utf-8"))
            self.assertEqual("missing", status["check"])

    def test_reimport_refuses_to_overwrite_a_locally_modified_generated_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            arguments = (
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
            )
            self.run_workflow(site, *arguments)
            article = (
                site
                / "drafts"
                / "2026-10-14-blog-from-logseq-test"
                / "article.md"
            )
            article.write_text(
                article.read_text(encoding="utf-8") + "\n本地手工修改。\n",
                encoding="utf-8",
            )
            before = article.read_bytes()
            self.push_logseq_update(root, "这是正文", "这是上游更新后的正文")

            result = self.run_workflow(
                site, *arguments, expected_returncode=2
            )

            self.assertEqual("error", result["status"])
            self.assertIn("本地生成草稿", "\n".join(result["errors"]))
            self.assertEqual(before, article.read_bytes())

    def test_import_blocks_a_missing_logseq_image_without_leaving_a_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.push_logseq_update(
                root,
                "../assets/image_123.png",
                "../assets/missing.png",
            )

            result = self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
                expected_returncode=2,
            )

            self.assertEqual("error", result["status"])
            self.assertIn("找不到 Logseq 图片", "\n".join(result["errors"]))
            self.assertFalse(
                (site / "drafts" / "2026-10-14-blog-from-logseq-test").exists()
            )

    def test_import_reports_git_pull_failure_as_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = root / "logseq-without-upstream"
            self.assertEqual(0, self.run_command("git", "init", str(logseq)).returncode)

            result = self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
                expected_returncode=2,
            )

            self.assertEqual("error", result["status"])
            self.assertIn("git pull --ff-only 失败", "\n".join(result["errors"]))
            self.assertFalse((site / "drafts").exists())

    def test_import_blocks_duplicate_logseq_slugs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            seed = root / "logseq-seed"
            duplicate = seed / "pages" / "Blog___重复文章.md"
            duplicate.write_text(
                (seed / "pages" / "Blog___测试文章.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.assertEqual(0, self.run_command("git", "add", str(duplicate), cwd=seed).returncode)
            self.assertEqual(
                0,
                self.run_command(
                    "git", "commit", "-m", "add duplicate slug", cwd=seed
                ).returncode,
            )
            self.assertEqual(0, self.run_command("git", "push", cwd=seed).returncode)

            result = self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
                expected_returncode=2,
            )

            self.assertEqual("error", result["status"])
            self.assertIn("存在重复 slug", "\n".join(result["errors"]))
            self.assertFalse((site / "drafts").exists())

    def test_slug_lookup_blocks_duplicate_local_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
            )
            imported = site / "drafts" / "2026-10-14-blog-from-logseq-test"
            legacy = site / "drafts" / "blog-from-logseq-test"
            legacy.mkdir()
            (legacy / "article.md").write_bytes((imported / "article.md").read_bytes())

            result = self.run_workflow(
                site,
                "status",
                "blog-from-logseq-test",
                expected_returncode=2,
            )

            self.assertEqual("error", result["status"])
            self.assertIn("重复草稿 slug", "\n".join(result["errors"]))

    def test_import_blocks_a_missing_created_property(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site = root / "site"
            site.mkdir()
            logseq = self.create_logseq_clone(root)
            self.push_logseq_update(
                root,
                "created:: [[2026-10-14]]",
                "created::",
            )

            result = self.run_workflow(
                site,
                "import-logseq",
                "blog-from-logseq-test",
                "--logseq-root",
                str(logseq),
                "--tag",
                "测试",
                expected_returncode=2,
            )

            self.assertEqual("error", result["status"])
            self.assertIn("created", "\n".join(result["errors"]))
            self.assertFalse((site / "drafts").exists())


if __name__ == "__main__":
    unittest.main()
