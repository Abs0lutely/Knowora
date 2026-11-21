# 结构力学自学知识点

面向大学生自学的知识点网站。每篇 HTML 文档独立呈现一个主题，网站首页按课程和主题整理文档。

## 本地构建与预览

需要 Python 3.10 或更新版本。构建脚本只使用 Python 标准库：

```bash
python scripts/build.py
python -m http.server 8000 --directory dist
```

然后打开 <http://localhost:8000>。构建产物在 `dist/`，不会提交到仓库。

## 内容目录

- `content/structural-mechanics/`：结构力学文档与课程信息。
- `content/tools/`：LaTeX 等工具教程。
- `site/templates/` 与 `site/assets/`：为后续站点外壳和自托管资源预留。
- `scripts/build.py`：生成静态首页并复制内容。
- `.github/workflows/deploy.yml`：推送到 `main` 后自动构建并发布到 GitHub Pages。

新增文档时，将独立 HTML 放入对应课程和章节目录，按现有格式添加 `doc-meta`，并在相应 `course.json` 中维护章节。确认首页、本地文档和交互内容正常后再提交。

教材版本与文档依据目前标为“待补充”，补全后更新课程信息及对应文档元信息。

## 许可

源代码采用 MIT License。`content/` 下的教学文档采用 CC BY-NC-SA 4.0，详情见 `content/LICENSE`。
