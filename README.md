# 照片图册

按年份编的几本可以翻页的照片书，一个主页选图册，点进去翻页阅读。

## 目录

```
index.html              主页：图册索引（由 build.py 生成）
library.css             主页样式
books/<年份>/index.html 每本图册（生成）
assets/photos/<年份>/   网页用压缩图（生成，长边 1400）
shared/                 翻页运行时、纸张与封面样式、字体
curation/2023.html      2023 那本手工编排的页序
books.json              书名、布面颜色、封面照片
build.py                生成脚本
photo/<年份>/           原始照片（不进 Git）
data/books.json         生成的书目数据
```

## 加照片、重新生成

1. 把照片放进 `photo/<年份>/`（新建年份也可以，需要在 `books.json` 里加一条）。
2. 运行：

```powershell
python build.py
```

脚本会按 EXIF 拍摄时间排序、压缩到长边 1400、按月份分组，重写主页和所有图册。
只加了几张时只会压缩新增的图片；要全部重压用 `python build.py --force`。

依赖：`pillow`（`pip install pillow`）。

## 改书名、封面、布面颜色

编辑 `books.json`：

```json
{ "year": "2024", "title": "山、老街与铁轨", "cloth": "#7a4f3d", "cover": "" }
```

- `title`：封面和主页上的书名
- `cloth`：布面颜色
- `cover`：封面照片的文件名，留空则自动挑一张颜色最丰富的
- `curated`：可选，指定一份手写页序（2023 就是这样保留的）

## 发布到 GitHub Pages

原始照片约 1 GB，**不要提交**。仓库里只放压缩后的 `assets/photos/`（约 40 MB）。
`.gitignore` 已经排除了 `photo/`。

```powershell
git init
git add .
git commit -m "照片图册"
git branch -M main
git remote add origin https://github.com/<用户名>/<仓库名>.git
git push -u origin main
```

然后仓库 **Settings → Pages**，Source 选 *Deploy from a branch*，分支 `main`、目录 `/ (root)`。
网址是 `https://<用户名>.github.io/<仓库名>/`。

也可以走 Actions：仓库里已带 `.github/workflows/pages.yml`，把 Pages 的 Source 改成
*GitHub Actions* 即可，之后每次 push 自动发布。

## 说明

- 页面尺寸 512 × 640，运行时按窗口缩放；手机上自动变成单页。
- 照片是懒加载的：只加载当前对开前后几页，照片再多也不会一次拉完。
- 原图只在本机 `photo/` 里，脚本只读不写。
