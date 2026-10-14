# Logseq → Zensical 博客文章 E2E 操作手册

本文用于由你亲自创建一篇测试文章，完整走通以下链路：

```text
Logseq 写作与图片
→ 自动提交并推送 Logseq
→ 将 status 改为 ready-to-publish
→ $publish-zensical-article 自动扫描队列并导入
→ 审稿
→ 通过或退稿重写
→ 确定性检查
→ 浏览器预览
→ 准备正式发布文件
→ 经确认后提交
→ 你手工推送
→ 线上验收
→ 删除测试文章并下线
```

手册以 Logseq 为发布前的唯一内容源。站点服务器上的导入稿是生成物，不要直接编辑。

> [!IMPORTANT]
> 本流程中的 Git 提交必须先由 AI 展示完整命令，并明确询问“确认执行吗？”。只有你回复 `y` 或 `yes` 后，AI 才能执行 `git add` 和 `git commit`。AI 永远不执行 `git push`。

> [!CAUTION]
> 如果站点仓库已有其他文章或首页的未提交改动，允许继续导入、审稿、检查和预览，但必须在 `prepare` 前停止。先收口旧改动或使用独立 worktree，不能覆盖或混入其他文章。

## 本次测试参数

开始前先填写这组参数，后续保持不变：

```text
文章标题：Logseq 博客 E2E 测试
Logseq 页面名：Blog/Logseq 博客 E2E 测试
创建日期：YYYY-MM-DD
slug：logseq-blog-e2e-YYYYMMDD
公开标签（blog-tags）：测试, Agent
预期分类：AI 与 Agent
```

约定：

- `slug` 只使用小写英文字母、数字和连字符。
- 为避免重名，建议把当天日期放在测试 slug 末尾。
- 日期只进入本地草稿目录，不进入公开 slug。
- Logseq 的 `tags` 是知识库内部分类，永远不作为公开博客标签。
- 公开标签只写在 `blog-tags::` 中，多个值用英文逗号分隔。
- `status:: ready-to-publish` 就是“请发布”信号；不需要再告诉 AI slug。

---

## 1. 前置检查：确认环境和工作区边界

### 操作

在 244 的站点仓库检查状态：

```bash
cd /root/project/all-in-one/code/nicelife729.github.io
git status --short
test -x .venv/bin/python
.venv/bin/python scripts/post_workflow.py --help
```

把开始前已有的修改记下来。重点检查：

```text
docs/index.md
docs/blog/posts/
tests/test_site.py
```

如果这些位置已有别的文章改动，告诉 AI：

```text
当前站点工作区已有其他改动。允许先完成本次文章的导入、审稿、检查和预览；
到 prepare 前必须停下并隔离，不能覆盖或混入现有改动。
```

### 预期

- Python 虚拟环境可用。
- CLI 能显示 `new`、`import-logseq`、`review`、`status`、`check`、`preview` 和 `prepare`。
- 已经知道哪些 Git 改动属于本次测试之前。

### Checklist

- [ ] 已确定唯一的标题、日期、slug 和公开标签。
- [ ] 已记录站点仓库开始前的 Git 状态。
- [ ] `.venv/bin/python` 可执行。
- [ ] 已确认是否需要在 `prepare` 前隔离 worktree。
- [ ] 没有把已有的 canary 或其他文章误认为本次测试内容。

---

## 2. 在 Logseq 创建文章并等待同步

### 操作

在 Logseq 中新建页面：

```text
Blog/Logseq 博客 E2E 测试
```

使用现有 `article` 模板。模板生成后的结构应类似：

```markdown
- {{renderer :smartblock, article_blog, New Smartblock, false}}
  - class:: article
    alias::
    tags:: #[[zzz-📤outbox 费曼输出/文章输出]]
    blog-tags:: 测试, Agent
    created:: [[YYYY-MM-DD]]
    slug:: logseq-blog-e2e-YYYYMMDD
    public:: false
    iteration::
    action::
    status:: writing
  - ## 摘要
    - 这是一篇用于验证 Logseq 到 Zensical 发布链路的测试文章。
  - ## 正文
    - 这是正文第一段。
    - 这是正文第二段。
    - ![有意义的图片说明](../assets/你的图片文件.png)
  - ## ref.
    - 可选的参考资料
```

写作要求：

- `class:: article`、`created` 和 `slug` 必须存在。
- `blog-tags` 至少包含一个公开标签。
- 写作时保持 `status:: writing`。
- `public:: false` 在 Logseq 写作阶段保持不变。
- 摘要和正文至少各写一段，方便检查首页摘要分隔。
- 插入一张真实图片，并把替代文本写成图片内容说明，不要使用 `image.png` 这类无意义文本。
- 测试文章不要包含密码、Token、私人地址、内网服务地址或真实隐私信息。

写完后先保存一次，确认 Logseq 自动提交和推送完成。然后把状态改为：

```text
status:: ready-to-publish
```

再次保存并等待同步。不要在站点服务器上手工复制页面或图片。

### 预期

- Logseq 页面保存成功。
- 页面和引用图片已经进入 Logseq 上游仓库。
- 同一个 slug 只出现在一个 `class:: article` 页面中。

### Checklist

- [ ] 页面使用 `Blog/` 命名空间。
- [ ] 已使用 `article` 模板。
- [ ] `class:: article`、日期和 slug 正确。
- [ ] 写作期间使用 `status:: writing`，完成后已改为 `ready-to-publish`。
- [ ] `blog-tags:: 测试, Agent`，`public:: false`。
- [ ] 摘要、正文和图片均已填写。
- [ ] 图片替代文本有实际意义。
- [ ] 已确认 Logseq 自动同步完成。
- [ ] 页面中没有凭证、私网地址或私人信息。

---

## 3. 使用 Skill 自动扫描待发布队列

### 操作

向 AI 发送：

```text
$publish-zensical-article

请按默认队列流程处理。不要提交，不要推送。
```

底层等价命令：

```bash
cd /root/project/all-in-one/code/nicelife729.github.io

.venv/bin/python scripts/post_workflow.py queue-logseq

.venv/bin/python scripts/post_workflow.py import-logseq \
  logseq-blog-e2e-YYYYMMDD

.venv/bin/python scripts/post_workflow.py status \
  logseq-blog-e2e-YYYYMMDD
```

队列命令会先在只读 Logseq 仓库执行 `git pull --ff-only`，只返回 `status:: ready-to-publish` 的 `class:: article` 页面，并按 `(created, slug)` 排序。Skill 会自动取得 slug，不再询问“要发哪一篇”。

预期生成：

```text
drafts/YYYY-MM-DD-logseq-blog-e2e-YYYYMMDD/
├── article.md
├── state.json
└── images/
    └── original/
        └── 你的图片文件.png
```

公开信息仍然是：

```text
slug: logseq-blog-e2e-YYYYMMDD
公开 URL 中不包含本地目录前面的 YYYY-MM-DD
```

不要直接修改导入后的 `article.md` 或 `images/original/`。需要改正文或图片时，回到 Logseq 修改并保存，然后重新运行同一条 `import-logseq`。

重复导入规则：

- 上游未变化：返回 `unchanged`，已完成阶段保持有效。
- 上游发生变化且本地生成物未被修改：安全刷新，并使旧审稿、检查和预览状态失效。
- 本地生成物被手工修改：阻断导入，不会静默覆盖。

### 预期

- 返回的草稿目录带日期前缀。
- front matter 的公开 slug 不带日期前缀。
- 标题、摘要、正文和参考资料转换正确。
- 只生成一个 `<!-- more -->`。
- Logseq 图片复制到 `images/original/`，正文引用有效。
- `git status --short` 不显示真实草稿和预览生成物。

### Checklist

- [ ] `git pull --ff-only` 成功。
- [ ] 只匹配到一个相同 slug 的 Logseq 页面。
- [ ] 实际目录为 `drafts/YYYY-MM-DD-<slug>/`。
- [ ] 公开 slug 与 Logseq 中一致且不带日期。
- [ ] 公开标签来自 `blog-tags`，没有泄漏 Logseq 内部 `tags`。
- [ ] 没有手工告诉 Skill 要发布哪个 slug。
- [ ] 标题、摘要、正文和图片转换正确。
- [ ] 恰好有一个 `<!-- more -->`。
- [ ] 没有直接编辑生成的 `article.md`。
- [ ] `status` 至少显示为已创建的私有草稿。

---

## 4. 完成审稿和确定性检查

### 操作

默认队列流程会直接进入审稿，不需要你再发一次 slug。审稿只覆盖结构与表达，不包含事实核验和外部网址真实性检查。

观察审稿结果：

- `pass`：Skill 在 `config/blog-categories.yml` 白名单中选择至多一个分类；没有明显匹配就不设置。随后自动继续 `check`。
- `needs-revision`：Skill 将具体反馈写入 `review.md`，记录当前内容指纹，并停止整个队列。未修改的同一内容不能再审或预览。

如果被退稿，亲自执行：

1. 回到 Logseq 把状态改为 `needs-revision`。
2. 根据 `review.md` 修改 Logseq 正文或图片；不要改站点服务器上的生成稿。
3. 修改完成后重新设置 `status:: ready-to-publish`，等待自动同步。
4. 再次只调用 `$publish-zensical-article`，确认新指纹可以重新审稿。

底层状态命令：

```bash
.venv/bin/python scripts/post_workflow.py status logseq-blog-e2e-YYYYMMDD
.venv/bin/python scripts/post_workflow.py review logseq-blog-e2e-YYYYMMDD --complete --verdict pass --category "AI 与 Agent"
.venv/bin/python scripts/post_workflow.py check logseq-blog-e2e-YYYYMMDD
```

### 预期

- `review.md` 中有具体意见，而不是空泛结论。
- 审稿前后 `article.md` 字节不变。
- 退稿时状态为 `review=needs_revision`，改稿后旧结论自动失效。
- 通过时状态为 `review=current`，分类只能来自白名单。
- `check` 返回空的 `errors`。
- advisories 被明确展示并由你决定是否处理。

### Checklist

- [ ] 已阅读全部结构与表达意见。
- [ ] 已明确审稿没有做事实核验。
- [ ] AI 没有擅自修改文章正文。
- [ ] 若测试了退稿，未修改的内容确实无法继续。
- [ ] 如修改过 Logseq，已重新设为 `ready-to-publish`并重跑 Skill。
- [ ] `review=current`。
- [ ] 分类为白名单中的 `AI 与 Agent`，或因不明显而省略。
- [ ] `check=current`。
- [ ] `errors` 为空。
- [ ] 图片存在、可读取且替代文本正确。
- [ ] 内部链接无失效。
- [ ] 外部事实与链接已由我人工确认。

---

## 5. 生成预览并执行浏览器 UAT

### 操作

向 AI 发送：

```text
$publish-zensical-article

请预览 logseq-blog-e2e-YYYYMMDD。
请自动恢复正确的 Chrome 预览隧道，并完成：
320px、常规手机和桌面宽度；
浅色和深色主题；
标题、日期、标签、正文、图片、评论区、页脚和站内导航；
控制台、网络请求和隐私检查。
不要截图，除非先征得我的同意。
```

底层预览命令：

```bash
cd /root/project/all-in-one/code/nicelife729.github.io
.venv/bin/python scripts/post_workflow.py preview logseq-blog-e2e-YYYYMMDD
.venv/bin/zensical serve --dev-addr 0.0.0.0:8137
```

必须使用 `preview` 返回的 URL，不要自己猜路径。

### 正确的 Chrome 网络拓扑

Chrome DevTools 控制的浏览器运行在 `192.168.2.248`。Chrome 中的 `127.0.0.1` 属于 248，不属于 244，也不属于 Air。

```text
244 上的 Zensical :8137
  ← SSH -R
248 上的 127.0.0.1:18137
  ← Chrome 访问
http://127.0.0.1:18137/<preview 返回的路径>
```

AI 可以从 244 自动建立转发：

```bash
ssh -fN \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R 127.0.0.1:18137:127.0.0.1:8137 \
  xuruijie@192.168.2.248
```

创建前应先检查 248 的 `18137`，已有可用转发时直接复用：

```bash
ssh -o BatchMode=yes xuruijie@192.168.2.248 \
  'lsof -nP -iTCP:18137 -sTCP:LISTEN || true'
```

### 预期

- `preview=current`。
- 320px、常规手机和桌面均无横向溢出。
- 图片加载成功并保持比例。
- 浅色和深色主题都清晰可读，评论区主题同步。
- 所有本地请求成功。
- 仅允许预期的第三方请求，例如 Giscus 和 GitHub 静态资源。
- 新测试文章没有 Giscus Discussion 时，Giscus 查询返回 404 和“Discussion not found”提示属于预期，不等于本地资源失败。
- 从相邻文章或文章列表进入测试文章并返回正常。

### Checklist

- [ ] 320px 深色模式正常。
- [ ] 常规手机宽度浅色模式正常。
- [ ] 桌面宽度浅色和深色模式正常。
- [ ] 页面没有横向滚动。
- [ ] 标题、日期、标签、摘要和正文正确。
- [ ] 图片清晰、无破图、顺序正确。
- [ ] 评论区、页脚和导航完整。
- [ ] 评论区主题随页面主题变化。
- [ ] 站内即时导航进入和返回正常。
- [ ] 控制台没有站点脚本错误。
- [ ] 没有失败的本地网络请求。
- [ ] 没有泄漏凭证、私人信息或意外私网地址。
- [ ] `review`、`check`、`preview` 都是 `current`。

---

## 6. 准备发布、提交、推送并线上验收

### 6.1 Prepare 前硬检查

先向 AI 发送：

```text
$publish-zensical-article

请检查 logseq-blog-e2e-YYYYMMDD 是否可以 prepare。
先比较当前 Git 状态与本次测试开始前的基线；
如果 docs/index.md 或目标发布目录有其他文章的改动，必须停止并隔离，不能覆盖。
```

只有工作区隔离成立后，才继续：

```text
$publish-zensical-article

请准备发布 logseq-blog-e2e-YYYYMMDD。
完成全部测试、严格构建、Git 差异、最终浏览器和隐私检查。
只准备文件，不要提交，不要推送。
```

底层命令：

```bash
.venv/bin/python scripts/post_workflow.py status logseq-blog-e2e-YYYYMMDD
.venv/bin/python scripts/post_workflow.py prepare logseq-blog-e2e-YYYYMMDD

.venv/bin/python -m unittest discover -s tests -v
.venv/bin/zensical build --clean --strict
git diff --check
git status --short
git diff
```

首次发布不要使用 `--overwrite`。只有明确更新已存在且由工作流管理的目录式文章时，才使用：

```bash
.venv/bin/python scripts/post_workflow.py prepare \
  logseq-blog-e2e-YYYYMMDD \
  --overwrite
```

### 6.2 提交硬检查点

Prepare 全部通过后，向 AI 发送：

```text
请使用 $commit-summary 生成这次测试文章的提交信息和精确命令。
只包含本次文章、首页和本次工作流必要文件；不要执行 push。
```

AI 必须先展示完整的、仓库限定的 `git add` 和 `git commit` 命令，然后询问：

```text
确认执行吗？
```

仅当你确认命令中的文件完全正确时，回复：

```text
y
```

其他回复都不能授权提交。

### 6.3 由你手工推送

提交成功后，你亲自执行：

```bash
cd /root/project/all-in-one/code/nicelife729.github.io
git push origin master
```

检查：

- GitHub Actions：<https://github.com/nicelife729/nicelife729.github.io/actions>
- 网站首页：<https://nicelife729.github.io/>

### 6.4 博客园同步验收

博客园同步源保持为：

```text
仓库：nicelife729.github.io
分支：master
文件夹：/docs/blog/posts
包含子文件夹：开
使用文件夹层级作为分类：关
启用 Markdown Front Matter：开
标题项：title
摘要项：description
标签项：tags
分类项：category
```

首次 E2E 保持“新随笔为草稿”，先在博客园后台检查内容和元数据，再手工发布。正式文章的 Front Matter 应包含小写 `title`、`description`、`tags`，以及本文选中时的单一 `category`。

### 预期

- 正式文章位于 `docs/blog/posts/<slug>/`。
- 正式文章没有 `draft: true`。
- 正式文章包含博客园所需的小写 Front Matter 字段。
- 首页“最新文章”指向测试文章。
- 真实草稿、state、review 和原图未进入 Git。
- Git 提交只包含审核过的目标文件。
- 用户 push 后 GitHub Actions 和 Pages 部署成功。

### Checklist

- [ ] Prepare 前已证明工作区隔离。
- [ ] `status` 显示阶段为 `prepared`，且 `prepared=current`。
- [ ] 全部自动化测试通过。
- [ ] strict build 显示 `No issues found`。
- [ ] `git diff --check` 无输出。
- [ ] 正式文章没有 `draft: true`。
- [ ] 首页卡片标题、日期、标签、摘要和链接正确。
- [ ] Git 差异只包含本次预期文件。
- [ ] `drafts/`、review、state 和原图没有被暂存。
- [ ] AI 展示了精确提交命令。
- [ ] 只有回复 `y` 或 `yes` 后才执行提交。
- [ ] `git push` 由我本人执行。
- [ ] GitHub Actions 成功。
- [ ] GitHub Pages 部署成功。
- [ ] 线上首页出现测试文章。
- [ ] 线上文章、图片、标签和评论区正常。
- [ ] 线上手机和桌面显示正常。
- [ ] 博客园已读到测试文章，标题、摘要、标签和分类正确。
- [ ] 线上验收后已将 Logseq 状态手工改为 `published`。

---

## 7. 删除测试文章并验证下线

线上验收通过后，使用独立提交让测试文章下线。不要把上线和下线压成一个提交，否则无法证明文章曾经成功部署。

### 操作

1. 记录测试文章正式目录和上线提交。
2. 使用编辑器或文件管理器删除准确的正式文章目录：

   ```text
   docs/blog/posts/logseq-blog-e2e-YYYYMMDD/
   ```

3. 不使用 `git rm`，不执行 rebase、force-push 或历史重写。
4. 将 `docs/index.md` 的“最新文章”恢复为测试文章之前的真实最新文章。
5. 保留受 Git 忽略的本地草稿，方便复查导入流程。
6. 重新执行完整门禁：

   ```bash
   .venv/bin/python -m unittest discover -s tests -v
   .venv/bin/zensical build --clean --strict
   git diff --check
   git status --short
   git diff
   ```

7. 使用 `$commit-summary` 生成独立的下线提交。
8. AI 仍须展示完整命令并等待你回复 `y` 或 `yes`。
9. 你亲自执行：

   ```bash
   git push origin master
   ```

10. 等待 GitHub Pages 部署完成，再检查首页和原文章 URL。
11. 在博客园检查同步结果，使用“取消发布”让随笔下线，不永久删除博文记录和评论。

### 预期

- 首页恢复为此前真实最新文章。
- 测试文章公开 URL 返回 404。
- 其他文章和资源不受影响。
- Git 历史保留一次上线提交和一次下线提交。
- Logseq 原稿和本地私有导入稿仍保留。
- 博客园随笔已取消发布，记录与评论仍保留。

### Checklist

- [ ] 已确认删除的是准确的测试文章目录。
- [ ] 首页恢复为此前真实最新文章。
- [ ] 没有删除 Logseq 原稿。
- [ ] 没有删除本地私有草稿。
- [ ] 没有使用 `git rm`、rebase、force-push 或 reset-hard。
- [ ] 下线前全部测试和严格构建通过。
- [ ] 下线使用独立提交。
- [ ] `git push` 由我本人执行。
- [ ] GitHub Pages 下线部署成功。
- [ ] 测试文章 URL 返回 404。
- [ ] 博客园随笔已取消发布，没有永久删除。
- [ ] 首页和其他文章正常。
- [ ] Git 历史仍能看到上线和下线过程。

---

## 故障处理与中止条件

### Logseq 拉取失败

停止导入。检查 Logseq 上游是否已经收到自动推送，以及服务器上的知识库仓库是否能执行：

```bash
git -C /root/project/all-in-one/knowledge-base/logseq pull --ff-only
```

不要跳过真实拉取，也不要改用手工复制冒充同步成功。

### 找不到 slug 或发现重复 slug

回到 Logseq 检查 `class:: article` 和 `slug::`。同一 slug 必须只存在一处；不要让 CLI 猜测。

### 图片缺失或路径越界

回到 Logseq 重新插入图片并等待同步。不要在站点生成目录中补一份同名文件绕过检查。

### 导入提示本地生成稿被修改

不要强制覆盖。先确认为什么有人直接修改了生成的 `article.md` 或原图，再决定保留哪一份内容。

### `review_pending` 或 `stale`

- `review_pending`：审稿报告尚未完成。
- `stale`：Logseq 内容或图片在后续阶段完成后又发生变化。

从最早失效的阶段重新执行，不要手工改 state。

### 严格构建后预览 URL 变成 404

`zensical build --clean --strict` 会重新生成正式站点并排除 `draft: true` 页面。重新运行：

```bash
.venv/bin/python scripts/post_workflow.py preview logseq-blog-e2e-YYYYMMDD
```

让常驻开发服务器重新增量生成草稿路由，然后再次验证 URL。

### Chrome 访问 `127.0.0.1:18137` 被拒绝

先确认 Chrome DevTools 的 `9222` 实际转发到 248，再检查 248 的 `18137`。不要把隧道建到 Air。

权威网络说明：

```text
/root/project/all-in-one/docs/ssh-passwordless-hosts.md
```

### Giscus 请求返回 404

如果本地资源全部成功，只有 Giscus 的 discussions API 因测试文章尚无 Discussion 返回 404，同时控制台提示将于首次评论时创建 Discussion，这是预期行为。

### Prepare 时工作区不干净

立即停止。先收口既有文章，或建立独立 worktree。不得：

- 覆盖已有 `docs/index.md` 改动。
- 把多个文章混进同一提交。
- 只靠部分暂存掩盖工作树语义冲突。
- 把自动化失败降级成警告。

### 任何自动化或浏览器检查失败

停止在当前阶段并让 AI 诊断。不要继续 `prepare`、提交或推送。

---

## 最终验收记录

完成后填写：

```text
Logseq 页面：
slug：
本地草稿目录：
本地预览 URL：
正式公开 URL：
上线提交：
上线部署时间：
下线提交：
下线部署时间：
最终结果：通过 / 不通过
备注：
```
