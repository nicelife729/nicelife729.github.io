# 克里斯许的碎碎念

基于 [Zensical](https://zensical.org/) 构建的个人主页与技术博客，部署于 GitHub Pages。

## 本地预览

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install zensical==0.0.69
zensical serve
```

## 验证与构建

```bash
python -m unittest discover -s tests -v
zensical build --clean
```

推送至 `master` 后，GitHub Actions 会自动测试、构建并发布 `site/` 目录。

## 旧站

2015 年的 Jekyll 站点保留在 Git 历史中，最后一个旧站提交为
`89ee2123680555880e1c9967993949207eaae05a`。
