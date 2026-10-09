from pathlib import Path
from html.parser import HTMLParser
import re
import subprocess
import sys
import unittest
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SITE_DIRECTORY = REPOSITORY_ROOT / "site"
ZENSICAL = Path(sys.executable).with_name("zensical")


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


class GeneratedSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [ZENSICAL, "build", "--clean"],
            cwd=REPOSITORY_ROOT,
            check=True,
        )

    def test_homepage_introduces_chris_xu(self) -> None:
        homepage = (SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")

        self.assertIn("克里斯许的碎碎念", homepage)
        self.assertIn("技术爱好者，关注 AI、开发工具与有趣的技术实践。", homepage)
        self.assertIn("AI 与智能 Agent", homepage)
        self.assertIn("开发工具与自动化", homepage)
        self.assertIn("自托管与个人基础设施", homepage)
        self.assertIn("https://github.com/nicelife729", homepage)

    def test_reader_can_find_the_first_post_and_its_tags(self) -> None:
        blog = (SITE_DIRECTORY / "blog" / "index.html").read_text(encoding="utf-8")

        self.assertIn("你好，这里是克里斯许的碎碎念", blog)

        matching_posts = [
            path
            for path in (SITE_DIRECTORY / "blog").rglob("index.html")
            if path.parent != SITE_DIRECTORY / "blog"
            and "archive" not in path.parts
            and "从一篇测试文章开始" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(1, len(matching_posts))

        post = matching_posts[0].read_text(encoding="utf-8")
        self.assertIn("AI", post)
        self.assertIn("随笔", post)

    def test_public_navigation_has_about_but_no_empty_projects_or_private_contact(self) -> None:
        homepage = (SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")
        about = (SITE_DIRECTORY / "about" / "index.html").read_text(encoding="utf-8")
        all_html = "\n".join(
            path.read_text(encoding="utf-8")
            for path in SITE_DIRECTORY.rglob("*.html")
        )

        self.assertRegex(homepage, re.compile(r">\s*首页\s*<"))
        self.assertRegex(homepage, re.compile(r">\s*文章\s*<"))
        self.assertRegex(homepage, re.compile(r">\s*关于\s*<"))
        self.assertNotRegex(homepage, re.compile(r">\s*项目\s*<"))
        self.assertIn("https://github.com/nicelife729", about)
        self.assertNotRegex(all_html, re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"))
        self.assertNotIn("disqus.com", all_html)

    def test_site_offers_both_light_and_dark_reading_modes(self) -> None:
        homepage = (SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")
        stylesheet = (
            SITE_DIRECTORY / "stylesheets" / "extra.css"
        ).read_text(encoding="utf-8")

        self.assertIn('data-md-color-scheme="default"', homepage)
        self.assertIn('data-md-color-scheme="slate"', homepage)
        self.assertIn("stylesheets/extra.css", homepage)
        self.assertIn(".home-hero", stylesheet)

    def test_giscus_comments_are_loaded_only_on_blog_posts(self) -> None:
        homepage = (SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")
        about = (SITE_DIRECTORY / "about" / "index.html").read_text(encoding="utf-8")
        post = next(
            path.read_text(encoding="utf-8")
            for path in (SITE_DIRECTORY / "blog").rglob("index.html")
            if "archive" not in path.parts
            and "从一篇测试文章开始" in path.read_text(encoding="utf-8")
            and path.parent != SITE_DIRECTORY / "blog"
        )

        self.assertIn("https://giscus.app/client.js", post)
        self.assertIn('data-repo="nicelife729/nicelife729.github.io"', post)
        self.assertNotIn("https://giscus.app/client.js", homepage)
        self.assertNotIn("https://giscus.app/client.js", about)

    def test_github_actions_builds_tests_and_deploys_the_site(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "docs.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("python -m unittest", workflow)
        self.assertIn("zensical==0.0.69", workflow)
        self.assertIn("zensical build --clean", workflow)
        self.assertIn("actions/upload-pages-artifact@v5", workflow)
        self.assertIn("actions/deploy-pages@v5", workflow)
        self.assertIn("path: site", workflow)

    def test_all_internal_links_resolve(self) -> None:
        errors = []

        for page in SITE_DIRECTORY.rglob("*.html"):
            parser = LinkParser()
            parser.feed(page.read_text(encoding="utf-8"))

            for href in parser.links:
                parts = urlsplit(href)
                if (
                    parts.scheme
                    or parts.netloc
                    or href.startswith(("#", "mailto:", "javascript:"))
                ):
                    continue

                path = unquote(parts.path)
                if path.startswith("/"):
                    target = (SITE_DIRECTORY / path.lstrip("/")).resolve()
                else:
                    target = (page.parent / path).resolve()

                if SITE_DIRECTORY.resolve() not in target.parents and target != SITE_DIRECTORY.resolve():
                    errors.append(f"{page.relative_to(SITE_DIRECTORY)} -> {href}")
                    continue

                if target.is_dir() or not target.suffix:
                    target = target / "index.html"
                if not target.exists():
                    errors.append(f"{page.relative_to(SITE_DIRECTORY)} -> {href}")

        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
