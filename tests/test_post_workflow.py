from __future__ import annotations

import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY_ROOT / "scripts" / "post_workflow.py"


class PostWorkflowTests(unittest.TestCase):
    def run_workflow(
        self, root: Path, *arguments: str, expected_returncode: int = 0
    ) -> dict[str, object]:
        completed = subprocess.run(
            [sys.executable, WORKFLOW, "--root", root, *arguments],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            expected_returncode,
            completed.returncode,
            completed.stderr or completed.stdout,
        )
        return json.loads(completed.stdout)

    def complete_review(self, root: Path, slug: str) -> dict[str, object]:
        report = root / "drafts" / slug / "review.md"
        content = report.read_text(encoding="utf-8")
        content = content.replace(
            "- 请在这里记录结构与叙事顺序建议；不直接修改正文。",
            "- 当前结构与叙事顺序可以进入检查阶段。",
        ).replace(
            "- 请在这里记录措辞、段落和术语建议；不直接修改正文。",
            "- 当前表达可以进入检查阶段。",
        )
        report.write_text(content, encoding="utf-8")
        return self.run_workflow(root, "review", slug, "--complete")

    def create_ready_draft(self, root: Path, slug: str = "ready-post") -> Path:
        homepage = root / "docs" / "index.md"
        homepage.parent.mkdir(parents=True, exist_ok=True)
        homepage.write_text(
            "# 首页\n\n"
            "<!-- latest-post:start -->\n"
            "旧内容\n"
            "<!-- latest-post:end -->\n",
            encoding="utf-8",
        )
        self.run_workflow(
            root,
            "new",
            "--title",
            "已经可以预览的文章",
            "--slug",
            slug,
            "--date",
            "2026-10-10",
        )
        article = root / "drafts" / slug / "article.md"
        article.write_text(
            article.read_text(encoding="utf-8")
            .replace("在这里写文章导语。", "这是发布摘要。")
            .replace("在这里开始正文。", "这是完整正文。"),
            encoding="utf-8",
        )
        self.run_workflow(root, "review", slug)
        self.complete_review(root, slug)
        self.run_workflow(root, "check", slug)
        self.run_workflow(root, "preview", slug)
        return article

    def test_writer_can_create_a_private_draft_from_a_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            result = self.run_workflow(
                root,
                "new",
                "--title",
                "让 Agent 真正进入工作流",
                "--slug",
                "agent-workflow",
                "--tag",
                "AI",
                "--date",
                "2026-10-10",
            )

            article = root / "drafts" / "agent-workflow" / "article.md"
            self.assertEqual("draft", result["status"])
            self.assertEqual("drafts/agent-workflow/article.md", result["article"])
            self.assertTrue(article.is_file())
            self.assertTrue(
                (root / "drafts" / "agent-workflow" / "images" / "original").is_dir()
            )
            content = article.read_text(encoding="utf-8")
            self.assertIn("draft: true", content)
            self.assertIn("comments: true", content)
            self.assertIn("slug: agent-workflow", content)
            self.assertIn("  - AI", content)
            self.assertIn("# 让 Agent 真正进入工作流", content)
            self.assertIn("<!-- more -->", content)

    def test_new_draft_derives_a_stable_slug_when_it_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            result = self.run_workflow(
                root,
                "new",
                "--title",
                "让 Agent 真正进入工作流",
                "--date",
                "2026-10-10",
            )

            self.assertEqual("让-agent-真正进入工作流", result["slug"])
            self.assertTrue(
                (root / "drafts" / "让-agent-真正进入工作流" / "article.md").is_file()
            )

    def test_new_draft_refuses_to_reuse_an_existing_draft_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "drafts" / "reserved" / "images" / "original"
            existing.mkdir(parents=True)
            sentinel = existing / "do-not-touch.png"
            sentinel.write_bytes(b"private-original")

            result = self.run_workflow(
                root,
                "new",
                "--title",
                "不能覆盖旧草稿",
                "--slug",
                "reserved",
                expected_returncode=2,
            )

            self.assertEqual("error", result["status"])
            self.assertIn("已经存在", "\n".join(result["errors"]))
            self.assertEqual(b"private-original", sentinel.read_bytes())
            self.assertFalse((root / "drafts" / "reserved" / "article.md").exists())

    def test_new_draft_refuses_a_slug_used_by_a_public_article(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            published = root / "docs" / "blog" / "posts" / "published.md"
            published.parent.mkdir(parents=True)
            published.write_text("# 已发布文章\n", encoding="utf-8")

            result = self.run_workflow(
                root,
                "new",
                "--title",
                "不能重复的文章",
                "--slug",
                "published",
                expected_returncode=2,
            )

            self.assertEqual("error", result["status"])
            self.assertIn("已被正式文章使用", "\n".join(result["errors"]))
            self.assertFalse((root / "drafts" / "published").exists())

    def test_review_creates_a_report_without_changing_the_article(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "一篇待审的文章",
                "--slug",
                "review-me",
                "--tag",
                "随笔",
                "--date",
                "2026-10-10",
            )
            article = root / "drafts" / "review-me" / "article.md"
            before = hashlib.sha256(article.read_bytes()).hexdigest()

            started = self.run_workflow(root, "review", "review-me")
            result = self.complete_review(root, "review-me")

            after = hashlib.sha256(article.read_bytes()).hexdigest()
            report = root / "drafts" / "review-me" / "review.md"
            self.assertEqual(before, after)
            self.assertEqual("review_pending", started["status"])
            self.assertEqual("reviewed", result["status"])
            self.assertTrue(report.is_file())
            review = report.read_text(encoding="utf-8")
            self.assertIn("## 阻断项", review)
            self.assertIn("## 结构建议", review)
            self.assertIn("## 表达建议", review)
            self.assertIn("## 发布检查", review)

    def test_preview_requires_a_completed_review_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "尚未写完审稿报告",
                "--slug",
                "pending-review",
            )
            self.run_workflow(root, "review", "pending-review")
            self.run_workflow(root, "check", "pending-review")

            pending = self.run_workflow(root, "status", "pending-review")
            blocked = self.run_workflow(
                root, "preview", "pending-review", expected_returncode=2
            )

            self.assertEqual("pending", pending["review"])
            self.assertIn("尚未完成审稿", "\n".join(blocked["errors"]))

    def test_status_invalidates_review_after_the_draft_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "会继续修改的文章",
                "--slug",
                "changing-post",
                "--date",
                "2026-10-10",
            )
            self.run_workflow(root, "review", "changing-post")
            self.complete_review(root, "changing-post")
            current = self.run_workflow(root, "status", "changing-post")
            self.assertEqual("current", current["review"])

            article = root / "drafts" / "changing-post" / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8") + "\n又补充了一段。\n",
                encoding="utf-8",
            )

            stale = self.run_workflow(root, "status", "changing-post")
            self.assertEqual("stale", stale["review"])
            self.assertEqual("draft", stale["status"])

    def test_status_reports_a_corrupt_state_file_as_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "状态文件损坏",
                "--slug",
                "broken-state",
            )
            state = root / "drafts" / "broken-state" / "state.json"
            state.write_text("{not-json", encoding="utf-8")

            result = self.run_workflow(
                root, "status", "broken-state", expected_returncode=2
            )

            self.assertEqual("error", result["status"])
            self.assertIn("state.json", "\n".join(result["errors"]))

    def test_check_blocks_missing_images_and_empty_alt_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "带图片的文章",
                "--slug",
                "image-post",
                "--date",
                "2026-10-10",
            )
            article = root / "drafts" / "image-post" / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。",
                    "正文内容。\n\n![](images/original/missing.png)",
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "image-post")
            self.complete_review(root, "image-post")

            result = self.run_workflow(
                root, "check", "image-post", expected_returncode=2
            )

            self.assertEqual("blocked", result["status"])
            errors = "\n".join(result["errors"])
            self.assertIn("替代文本", errors)
            self.assertIn("missing.png", errors)

    def test_preview_optimizes_an_image_without_changing_the_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "图片优化测试",
                "--slug",
                "optimized-image",
                "--date",
                "2026-10-10",
            )
            draft = root / "drafts" / "optimized-image"
            article = draft / "article.md"
            source = draft / "images" / "original" / "wide.jpg"
            Image.new("RGB", (2400, 1200), "#4f8cff").save(source, quality=95)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。",
                    "正文内容。\n\n![蓝色宽图](images/original/wide.jpg)",
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "optimized-image")
            self.complete_review(root, "optimized-image")
            self.run_workflow(root, "check", "optimized-image")

            result = self.run_workflow(root, "preview", "optimized-image")

            preview = root / "docs" / "blog" / "posts" / "drafts" / "optimized-image"
            generated = preview / "images" / "wide.webp"
            self.assertEqual("previewed", result["status"])
            self.assertEqual(
                "/blog/2026/10/10/optimized-image/", result["url"]
            )
            self.assertTrue(generated.is_file())
            with Image.open(generated) as image:
                self.assertEqual((1600, 800), image.size)
                self.assertEqual("WEBP", image.format)
            self.assertEqual(original_hash, hashlib.sha256(source.read_bytes()).hexdigest())
            rendered = (preview / "index.md").read_text(encoding="utf-8")
            self.assertIn("draft: true", rendered)
            self.assertIn("![蓝色宽图](images/wide.webp)", rendered)
            report = (draft / "review.md").read_text(encoding="utf-8")
            self.assertIn("wide.jpg", report)
            self.assertIn("wide.webp", report)
            self.assertIn("原始字节", report)
            self.assertIn("发布字节", report)

    def test_prepare_generates_the_public_post_and_updates_the_homepage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            homepage = root / "docs" / "index.md"
            homepage.parent.mkdir(parents=True)
            homepage.write_text(
                "# 首页\n\n"
                "<!-- latest-post:start -->\n"
                "旧内容\n"
                "<!-- latest-post:end -->\n",
                encoding="utf-8",
            )
            self.run_workflow(
                root,
                "new",
                "--title",
                "从草稿正式发布",
                "--slug",
                "publish-me",
                "--tag",
                "AI",
                "--tag",
                "自动化",
                "--date",
                "2026-10-10",
            )
            article = root / "drafts" / "publish-me" / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8")
                .replace("在这里写文章导语。", "这是一段会出现在首页的摘要。")
                .replace("在这里开始正文。", "这里是已经完成的正文。"),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "publish-me")
            self.complete_review(root, "publish-me")
            self.run_workflow(root, "check", "publish-me")
            self.run_workflow(root, "preview", "publish-me")

            result = self.run_workflow(root, "prepare", "publish-me")

            published = root / "docs" / "blog" / "posts" / "publish-me" / "index.md"
            self.assertEqual("prepared", result["status"])
            self.assertTrue(published.is_file())
            self.assertFalse(
                (root / "docs" / "blog" / "posts" / "drafts" / "publish-me").exists()
            )
            public_content = published.read_text(encoding="utf-8")
            self.assertNotIn("draft: true", public_content)
            self.assertIn("slug: publish-me", public_content)
            homepage_content = homepage.read_text(encoding="utf-8")
            self.assertIn("[从草稿正式发布](blog/posts/publish-me/index.md)", homepage_content)
            self.assertIn("2026 年 10 月 10 日", homepage_content)
            self.assertIn("home-post-tag\">AI", homepage_content)
            self.assertIn("这是一段会出现在首页的摘要。", homepage_content)

    def test_check_blocks_a_corrupt_raster_image_before_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "损坏图片测试",
                "--slug",
                "broken-image",
                "--date",
                "2026-10-10",
            )
            draft = root / "drafts" / "broken-image"
            source = draft / "images" / "original" / "broken.png"
            source.write_bytes(b"not a png")
            article = draft / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。",
                    "正文。\n\n![损坏图片](images/original/broken.png)",
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "broken-image")
            self.complete_review(root, "broken-image")

            result = self.run_workflow(
                root, "check", "broken-image", expected_returncode=2
            )

            self.assertIn("无法读取图片", "\n".join(result["errors"]))

    def test_preview_supports_html_images_and_rewrites_the_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "HTML 图片测试",
                "--slug",
                "html-image",
                "--date",
                "2026-10-10",
            )
            draft = root / "drafts" / "html-image"
            source = draft / "images" / "original" / "raw.png"
            Image.new("RGBA", (32, 32), (79, 140, 255, 128)).save(source)
            article = draft / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。",
                    '<img src="images/original/raw.png" alt="半透明蓝色方块">',
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "html-image")
            self.complete_review(root, "html-image")
            self.run_workflow(root, "check", "html-image")

            self.run_workflow(root, "preview", "html-image")

            preview = root / "docs" / "blog" / "posts" / "drafts" / "html-image"
            rendered = (preview / "index.md").read_text(encoding="utf-8")
            self.assertIn('src="images/raw.webp"', rendered)
            self.assertTrue((preview / "images" / "raw.webp").is_file())

    def test_check_blocks_an_html_image_without_alt_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "HTML 替代文本测试",
                "--slug",
                "html-alt",
            )
            draft = root / "drafts" / "html-alt"
            source = draft / "images" / "original" / "raw.png"
            Image.new("RGB", (8, 8), "blue").save(source)
            article = draft / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。", '<img src="images/original/raw.png">'
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "html-alt")
            self.complete_review(root, "html-alt")

            result = self.run_workflow(
                root, "check", "html-alt", expected_returncode=2
            )

            self.assertIn("HTML 图片", "\n".join(result["errors"]))
            self.assertIn("替代文本", "\n".join(result["errors"]))

    def test_check_blocks_images_outside_the_draft_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "目录越界测试",
                "--slug",
                "escaped-image",
            )
            outside = root / "drafts" / "outside.png"
            Image.new("RGB", (8, 8), "red").save(outside)
            article = root / "drafts" / "escaped-image" / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。", "![越界图片](../outside.png)"
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "escaped-image")
            self.complete_review(root, "escaped-image")

            result = self.run_workflow(
                root, "check", "escaped-image", expected_returncode=2
            )

            self.assertIn("越过草稿目录", "\n".join(result["errors"]))

    def test_check_blocks_missing_internal_links_and_advises_on_external_links(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "about.md").write_text("# 关于\n", encoding="utf-8")
            self.run_workflow(
                root,
                "new",
                "--title",
                "链接检查测试",
                "--slug",
                "checked-links",
            )
            article = root / "drafts" / "checked-links" / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。",
                    "[关于我](/about/)\n\n"
                    "[丢失页面](/missing/)\n\n"
                    "[Zensical](https://zensical.org/)",
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "checked-links")
            self.complete_review(root, "checked-links")

            result = self.run_workflow(
                root, "check", "checked-links", expected_returncode=2
            )

            self.assertIn("找不到内部链接目标：/missing/", "\n".join(result["errors"]))
            self.assertNotIn("/about/", "\n".join(result["errors"]))
            self.assertIn("外部链接", "\n".join(result["advisories"]))
            self.assertIn("https://zensical.org/", "\n".join(result["advisories"]))

    def test_check_blocks_image_output_name_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "图片同名测试",
                "--slug",
                "image-collision",
            )
            draft = root / "drafts" / "image-collision"
            first = draft / "images" / "original" / "one" / "same.png"
            second = draft / "images" / "original" / "two" / "same.jpg"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            Image.new("RGB", (8, 8), "red").save(first)
            Image.new("RGB", (8, 8), "blue").save(second)
            article = draft / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。",
                    "![红色](images/original/one/same.png)\n\n"
                    "![蓝色](images/original/two/same.jpg)",
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "image-collision")
            self.complete_review(root, "image-collision")

            result = self.run_workflow(
                root, "check", "image-collision", expected_returncode=2
            )

            self.assertIn("图片输出文件名冲突", "\n".join(result["errors"]))

    def test_preview_preserves_svg_and_animated_gif_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.run_workflow(
                root,
                "new",
                "--title",
                "保留原格式测试",
                "--slug",
                "preserved-images",
            )
            draft = root / "drafts" / "preserved-images"
            svg = draft / "images" / "original" / "diagram.svg"
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                '<rect width="10" height="10" fill="blue"/></svg>',
                encoding="utf-8",
            )
            gif = draft / "images" / "original" / "motion.gif"
            frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
            frames[0].save(
                gif,
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
            )
            svg_hash = hashlib.sha256(svg.read_bytes()).hexdigest()
            gif_hash = hashlib.sha256(gif.read_bytes()).hexdigest()
            article = draft / "article.md"
            article.write_text(
                article.read_text(encoding="utf-8").replace(
                    "在这里开始正文。",
                    "![架构图](images/original/diagram.svg)\n\n"
                    "![动图](images/original/motion.gif)",
                ),
                encoding="utf-8",
            )
            self.run_workflow(root, "review", "preserved-images")
            self.complete_review(root, "preserved-images")
            self.run_workflow(root, "check", "preserved-images")

            self.run_workflow(root, "preview", "preserved-images")

            images = (
                root
                / "docs"
                / "blog"
                / "posts"
                / "drafts"
                / "preserved-images"
                / "images"
            )
            self.assertEqual(svg_hash, hashlib.sha256((images / "diagram.svg").read_bytes()).hexdigest())
            self.assertEqual(gif_hash, hashlib.sha256((images / "motion.gif").read_bytes()).hexdigest())

    def test_prepare_is_invalidated_when_content_changes_after_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            article = self.create_ready_draft(root, "stale-preview")
            article.write_text(
                article.read_text(encoding="utf-8") + "\n预览后新增的内容。\n",
                encoding="utf-8",
            )

            result = self.run_workflow(
                root, "prepare", "stale-preview", expected_returncode=2
            )

            self.assertEqual("blocked", result["status"])
            errors = "\n".join(result["errors"])
            self.assertIn("审稿结果已经失效", errors)
            self.assertIn("预览结果已经失效", errors)
            self.assertFalse(
                (root / "docs" / "blog" / "posts" / "stale-preview").exists()
            )

    def test_prepare_requires_explicit_overwrite_for_an_existing_post(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_ready_draft(root, "updated-post")
            self.run_workflow(root, "prepare", "updated-post")

            blocked = self.run_workflow(
                root, "prepare", "updated-post", expected_returncode=2
            )
            self.assertIn("--overwrite", "\n".join(blocked["errors"]))

            updated = self.run_workflow(
                root, "prepare", "updated-post", "--overwrite"
            )
            self.assertEqual("prepared", updated["status"])

    def test_prepare_refuses_to_overwrite_a_publication_with_unknown_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_ready_draft(root, "drifted-post")
            self.run_workflow(root, "prepare", "drifted-post")
            destination = root / "docs" / "blog" / "posts" / "drifted-post"
            unknown = destination / "manual-note.txt"
            unknown.write_text("手工维护内容", encoding="utf-8")

            result = self.run_workflow(
                root,
                "prepare",
                "drifted-post",
                "--overwrite",
                expected_returncode=2,
            )

            self.assertEqual("blocked", result["status"])
            self.assertIn("存在工作流未管理的文件", "\n".join(result["errors"]))
            self.assertEqual("手工维护内容", unknown.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
