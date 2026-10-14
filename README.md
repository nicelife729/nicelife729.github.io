# 克里斯许的碎碎念

基于 [Zensical](https://zensical.org/) 构建的个人主页与技术博客，部署于 GitHub Pages。

## 本地预览

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
zensical serve
```

## 验证与构建

```bash
python -m unittest discover -s tests -v
zensical build --clean --strict
```

推送至 `master` 后，GitHub Actions 会自动测试、构建并发布 `site/` 目录。

## 文章工作流

草稿保存在被 Git 忽略的 `drafts/` 目录。通过文章发布 Skill 使用自然语言完成新建、审稿、检查、预览和准备发布；确定性操作也可以直接调用：

```bash
python scripts/post_workflow.py new --title "文章标题" --slug article-slug --tag 随笔
python scripts/post_workflow.py queue-logseq
python scripts/post_workflow.py import-logseq article-slug
python scripts/post_workflow.py review article-slug
# 填写命令返回的日期前缀草稿目录中的 review.md 后：
python scripts/post_workflow.py review article-slug --complete --verdict pass --category "AI 与 Agent"
python scripts/post_workflow.py check article-slug
python scripts/post_workflow.py preview article-slug
python scripts/post_workflow.py status article-slug
python scripts/post_workflow.py prepare article-slug
```

`new` 和 `import-logseq` 都把创建日期用于本地排序，但日期不会进入公开
URL。每篇文章的本地工作区如下：

```text
drafts/YYYY-MM-DD-<slug>/
├── article.md             # 规范化正文；Logseq 导入时为生成物
├── review.md              # 审稿建议与发布检查报告
├── state.json             # 阶段状态和内容指纹
└── images/original/       # 永不覆盖、永不发布的原图
```

旧的 `drafts/<slug>/` 草稿仍可通过公开 slug 使用，不需要迁移。工作流会读取
front matter 的 `slug` 定位草稿；若多个目录声明同一 slug，会阻断而不是猜测。

`drafts/_template/article.md` 是可复制的本地 Markdown 模板。通过 Logseq 写作时，
使用 `class:: article` 模板并保存到上游；`import-logseq` 会先对只读知识库执行
`git pull --ff-only`，再按 slug 导入摘要、正文、参考资料和 `assets` 图片。公开标签写在
`blog-tags::` 属性中（例如 `blog-tags:: AI, Agent`）；Logseq 的 `tags` 只用于知识库内部分类，不会泄漏到博客。
`queue-logseq` 只返回 `status:: ready-to-publish` 的文章；空队列是正常结果，缺少
`slug`/`created`/`blog-tags` 或存在重复 slug 会整体阻断。Logseq 在发布前是内容源，本地导入稿不应手工编辑；重复导入只会
覆盖仍与上次导入指纹一致的生成稿，检测到本地改动时会阻断。

审稿只生成 `review.md`，不会修改正文，也不会联网做事实核验。完成时必须给出
`--verdict pass` 或 `--verdict needs-revision`。退稿会记录反馈和内容指纹，未修改前不能继续；
应回到 Logseq 重写后再导入、重审。通过时可从 `config/blog-categories.yml` 白名单选择至多一个
`--category`；没有明显归属就省略。正文或原图变化后，旧的审稿、检查和预览状态会自动失效。JPEG/PNG 会生成 WebP 发布副本，宽度上限为 1600 像素；SVG、GIF 和已有 WebP 原样复制。缺图、缺少替代文本、越界路径、损坏图片、内部死链和输出文件名冲突都会阻断发布，外部链接只给出提示。

`preview` 生成被 Git 忽略且保留 `draft: true` 的本地页面。`prepare` 只有在当前内容依次通过审稿、检查和预览后，才会生成正式文章、移除草稿标记并更新首页“最新文章”区块。已有正式文章默认不会被覆盖，确认更新时显式使用：

```bash
python scripts/post_workflow.py prepare article-slug --overwrite
```

更新既有目录式文章时，`prepare --overwrite` 还会核对上一次生成的文件清单；目录中出现手工文件或内容漂移时会拒绝覆盖。旧式 `docs/blog/posts/<slug>.md` 文章需要先显式迁移，不能被新工作流静默覆盖。

`prepare` 只准备待提交文件，不会执行 Git 提交或推送。正式文章会同时生成博客园可读的小写
Front Matter：`title`、`description`、`tags`，以及审稿时选定的可选 `category`。

## 旧站

2015 年的 Jekyll 站点保留在 Git 历史中，最后一个旧站提交为
`89ee2123680555880e1c9967993949207eaae05a`。
