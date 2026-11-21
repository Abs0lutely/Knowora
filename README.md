# Knowora 知识点网站

面向大学生自学的知识点网站。每篇 HTML 文档自包含地讲解一个主题；网站提供课程目录、标签、最近更新和知识点搜索。

## 在线网站

[打开 Knowora 知识点网站](https://abs0lutely.github.io/Knowora/)

## 本地构建与预览

需要 Python 3.10 或更新版本。构建脚本只使用 Python 标准库：

```bash
python scripts/build.py
python -m http.server 8000 --directory dist
```

然后打开 <http://localhost:8000>。构建产物在 `dist/`，不会提交到仓库。

## 内容与构建

- `content/structural-mechanics/`：结构力学文档与课程信息。
- `content/tools/`：LaTeX 等工具教程。
- `site/templates/` 与 `site/assets/`：站点共享资源；字体和 MathJax 已自托管。
- `scripts/build.py`：校验元信息与引用，生成课程、标签、最近更新、搜索索引和文档外壳。
- `.github/workflows/deploy.yml`：推送到 `main` 后自动构建并发布到 GitHub Pages。

构建脚本仅使用 Python 标准库。缺失字段、无效日期、不存在的前置或相关文档、超大文档和 HTML 外部网址会使构建失败；`待补充`/`不适用` 教材或来源值会显示提示并允许构建，便于后续补齐。

新增文档时，将独立 HTML 放入对应课程和章节目录，按现有格式添加 `doc-meta`，并在相应 `course.json` 中维护章节。前置知识和相关知识点填写 `课程 ID/文件名`，例如 `structural-mechanics/frame-displacement-method-from-zero`。确认首页、本地文档和交互内容正常后再提交。

教材版本与文档依据目前标为“待补充”，补全后更新课程信息及对应文档元信息。

## 许可

源代码采用 MIT License。`content/` 下的教学文档采用 CC BY-NC-SA 4.0，详情见 `content/LICENSE`。
