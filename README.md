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
python scripts/post_workflow.py review article-slug
# 填写 drafts/article-slug/review.md 后：
python scripts/post_workflow.py review article-slug --complete
python scripts/post_workflow.py check article-slug
python scripts/post_workflow.py preview article-slug
python scripts/post_workflow.py status article-slug
python scripts/post_workflow.py prepare article-slug
```

每篇文章的本地工作区如下：

```text
drafts/<slug>/
├── article.md             # 唯一手写正文源
├── review.md              # 审稿建议与发布检查报告
├── state.json             # 阶段状态和内容指纹
└── images/original/       # 永不覆盖、永不发布的原图
```

审稿只生成 `review.md`，不会修改正文，也不会联网做事实核验。首次执行 `review` 后状态为 `review_pending`；填写完结构与表达建议并执行 `review --complete`，当前内容才会被标记为已审。正文或原图变化后，旧的审稿、检查和预览状态会自动失效。JPEG/PNG 会生成 WebP 发布副本，宽度上限为 1600 像素；SVG、GIF 和已有 WebP 原样复制。缺图、缺少替代文本、越界路径、损坏图片、内部死链和输出文件名冲突都会阻断发布，外部链接只给出提示。

`preview` 生成被 Git 忽略且保留 `draft: true` 的本地页面。`prepare` 只有在当前内容依次通过审稿、检查和预览后，才会生成正式文章、移除草稿标记并更新首页“最新文章”区块。已有正式文章默认不会被覆盖，确认更新时显式使用：

```bash
python scripts/post_workflow.py prepare article-slug --overwrite
```

更新既有目录式文章时，`prepare --overwrite` 还会核对上一次生成的文件清单；目录中出现手工文件或内容漂移时会拒绝覆盖。旧式 `docs/blog/posts/<slug>.md` 文章需要先显式迁移，不能被新工作流静默覆盖。

`prepare` 只准备待提交文件，不会执行 Git 提交或推送。

## 旧站

2015 年的 Jekyll 站点保留在 Git 历史中，最后一个旧站提交为
`89ee2123680555880e1c9967993949207eaae05a`。
