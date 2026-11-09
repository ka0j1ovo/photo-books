# -*- coding: utf-8 -*-
"""
把 photo/<年份>/ 里的照片编成一本本可以翻页的图册。

    python build.py                # 用当前目录的 photo/ 和 books.json 重新生成
    python build.py --force        # 忽略缓存，重新压缩所有照片

生成物：
    index.html              图册索引（主页）
    books/<年份>/index.html 每本图册
    assets/photos/<年份>/   压缩后的网页用图
原始照片不会被修改，也不需要提交到 Git。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime

from PIL import Image, ImageOps, ImageStat

ROOT = os.path.dirname(os.path.abspath(__file__))
PAGE_W, PAGE_H = 512, 640
MAX_EDGE = 1400
QUALITY = 82

MONTHS_CN = ["一月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月"]
DIGITS_CN = str.maketrans("0123456789", "〇一二三四五六七八九")


def cn_year(year: str) -> str:
    return year.translate(DIGITS_CN)


def esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def exif_datetime(path: str) -> datetime | None:
    try:
        image = Image.open(path)
        exif = image.getexif()
        raw = exif.get(36867) or exif.get(306)
        if raw:
            return datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    try:
        return datetime.fromtimestamp(os.path.getmtime(path))
    except Exception:
        return None


def exif_datetime_hard(path: str) -> datetime | None:
    """只读 EXIF，没有就返回 None。"""
    try:
        exif = Image.open(path).getexif()
        raw = exif.get(36867) or exif.get(306)
        if raw:
            return datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None
    return None


def colorfulness(image: Image.Image) -> float:
    small = image.resize((48, 48))
    pixels = list(small.getdata())
    rg = [p[0] - p[1] for p in pixels]
    yb = [0.5 * (p[0] + p[1]) - p[2] for p in pixels]
    def mean(values):
        return sum(values) / len(values)
    def std(values):
        m = mean(values)
        return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5
    return (std(rg) + std(yb)) + 0.3 * ((mean(rg) ** 2 + mean(yb) ** 2) ** 0.5)


def average_color(image: Image.Image) -> str:
    stat = ImageStat.Stat(image.resize((8, 8)))
    r, g, b = (int(v) for v in stat.mean[:3])
    return f"rgb({r} {g} {b})"


def optimize(src: str, dst: str, force: bool) -> dict:
    """压到长边 MAX_EDGE；返回尺寸、比例、主色。"""
    need = force or not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src)
    if need:
        image = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        image.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    image = Image.open(dst).convert("RGB")
    w, h = image.size
    return {"w": w, "h": h, "aspect": w / h, "color": average_color(image), "score": colorfulness(image)}


def inspect_source(src: str) -> dict:
    """只为取尺寸、比例和主色，不写文件（手工编排的书用）。"""
    image = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    w, h = image.size
    small = image.copy()
    small.thumbnail((800, 800), Image.LANCZOS)
    return {"w": w, "h": h, "aspect": w / h, "color": average_color(small), "score": colorfulness(small)}


def dhash(image: Image.Image) -> int:
    small = image.convert("L").resize((9, 8), Image.LANCZOS)
    pixels = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if pixels[row * 9 + col] > pixels[row * 9 + col + 1] else 0)
    return bits


def distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def drop_bursts(photos: list[dict], limit: int = 1, threshold: int = 6) -> tuple[list[dict], int]:
    """同一场景的连拍最多留两张，避免整本书都是几乎一样的画面。"""
    kept: list[dict] = []
    run = 0
    for photo in photos:
        if kept and distance(photo["hash"], kept[-1]["hash"]) <= threshold:
            run += 1
            if run >= limit:
                photo["skipped"] = True
                continue
        else:
            run = 0
        kept.append(photo)
    return kept, len(photos) - len(kept)


def collect(year_dir: str, out_dir: str, force: bool, write: bool = True) -> list[dict]:
    files = [f for f in os.listdir(year_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    photos = []
    missing = []
    for name in files:
        src = os.path.join(year_dir, name)
        dt = exif_datetime_hard(src)
        if dt is None:
            missing.append({"src": src, "name": name})
        else:
            photos.append({"src": src, "name": name, "dt": dt})
    # 没有 EXIF 的照片：用文件时间，但不要因为拷贝时间而跑到年底。
    latest = max((p["dt"] for p in photos), default=None)
    for photo in missing:
        stamp = datetime.fromtimestamp(os.path.getmtime(photo["src"]))
        if latest and stamp > latest:
            stamp = latest
        photo["dt"] = stamp
        photos.append(photo)
    photos.sort(key=lambda p: (p["dt"], p["name"]))
    for index, photo in enumerate(photos, start=1):
        if write:
            out_name = f"{index:03d}.jpg"
            meta = optimize(photo["src"], os.path.join(out_dir, out_name), force)
        else:
            out_name = photo["name"]
            meta = inspect_source(photo["src"])
        photo.update(meta)
        photo["file"] = out_name
        photo["hash"] = dhash(Image.open(os.path.join(out_dir, out_name) if write else photo["src"]))
        photo["caption"] = f"{photo['dt'].month}月{photo['dt'].day}日 {photo['dt'].strftime('%H:%M')}"
        photo["alt"] = f"{photo['dt'].year}年{photo['dt'].month}月{photo['dt'].day}日 {photo['dt'].strftime('%H:%M')} 拍摄的照片"
    return photos


def date_range(photos: list[dict]) -> str:
    first, last = photos[0]["dt"], photos[-1]["dt"]
    if first.year == last.year:
        return f"{first.year} 年 {first.month} 月 — {last.month} 月"
    return f"{first.year} 年 {first.month} 月 — {last.year} 年 {last.month} 月"


def pick_cover(photos: list[dict], wanted: str) -> dict:
    if wanted:
        for photo in photos:
            if photo["name"] == wanted or photo["file"] == wanted:
                return photo
    landscape = [p for p in photos if p["aspect"] >= 1.1] or photos
    return max(landscape, key=lambda p: p["score"])


def cover_page(book: dict, cover: dict, base: str) -> str:
    return f'''<article class="book-page art-page cloth recto" data-density="hard" aria-label="封面">
  <h2 class="cover-title">{esc(book["title"])}</h2>
  <p class="cover-subtitle">{esc(book["subtitle"])}</p>
  <span class="cover-rule" aria-hidden="true"></span>
  <figure class="cover-plate"><img src="{base}assets/photos/{book["year"]}/{cover["file"]}" alt=""></figure>
  <p class="cover-foot">PHOTOGRAPHS · {book["year"]}</p>
</article>'''


def title_page(book: dict) -> str:
    return f'''<article class="book-page art-page paper recto" aria-label="扉页">
  <div class="title-block">
    <h2>{esc(book["title"])}</h2>
    <p>照片 {cn_year(book["year"])}</p>
  </div>
  <p class="epigraph">{esc(book["subtitle"])} · {book["count"]} 张</p>
  <p class="imprint">PHOTOGRAPHS</p>
</article>'''


def divider_page(month: int, year: int, count: int) -> str:
    return f'''<article class="book-page art-page paper divider" aria-label="{month} 月">
  <p class="month">{MONTHS_CN[month - 1]}</p>
  <span class="month-rule" aria-hidden="true"></span>
  <p class="month-meta">{year} · {count} 张</p>
</article>'''


def photo_page(book: dict, photo: dict, index: int, base: str) -> str:
    aspect = photo["aspect"]
    src = f'{base}assets/photos/{book["year"]}/{photo["file"]}'
    img = f'<img data-src="{src}" width="{photo["w"]}" height="{photo["h"]}" alt="{esc(photo["alt"])}" style="background:{photo["color"]}">'

    if aspect >= 1.12 and index % 9 == 4:
        return f'<article class="book-page art-page bleed-page" aria-label="{esc(photo["caption"])}">\n  {img}\n</article>'

    if aspect >= 1.15:
        cap = 88
    elif aspect >= 0.92:
        cap = 76
    else:
        cap = 66
    width = max(40, min(cap, int(82 * aspect)))
    top = 47
    if index % 7 == 3:
        width = max(36, int(width * 0.78))
        top = 44
    elif index % 5 == 2:
        top = 42

    return f'''<article class="book-page art-page paper" aria-label="{esc(photo["caption"])}">
  <figure class="figure" style="width:{width}%;top:{top}%">
    {img}
    <figcaption>{esc(photo["caption"])}</figcaption>
  </figure>
</article>'''


def month_chapters(photos: list[dict]) -> list[dict]:
    chapters: list[dict] = []
    for photo in photos:
        key = (photo["dt"].year, photo["dt"].month)
        if not chapters or chapters[-1]["key"] != key:
            chapters.append({"key": key, "photos": []})
        chapters[-1]["photos"].append(photo)
    return chapters


def colophon_page(book: dict) -> str:
    extra = ""
    if book.get("skipped"):
        extra = f"其中 {book['skipped']} 张与相邻照片几乎相同的连拍没有收进来。"
    return f'''<article class="book-page art-page paper" aria-label="版权页">
  <div class="colophon">
    <h3>{esc(book["title"])}</h3>
    <p>照片 {cn_year(book["year"])} · {esc(book["subtitle"])}</p>
    <p class="small-print">共 {book["count"]} 张照片，按拍摄时间排列。{extra}网页使用压缩副本，原始文件保存在 photo/{book["year"]}/ 内，没有改动。</p>
    <p class="small-print">PHOTOGRAPHS · {book["year"]}</p>
  </div>
</article>'''


def back_cover(book: dict) -> str:
    return f'''<article class="book-page art-page cloth verso" data-density="hard" aria-label="封底">
  <span class="back-mark">{esc(book["title"])} · {book["year"]}</span>
</article>'''


def blank_page() -> str:
    return '<article class="book-page art-page endpaper" aria-label="环衬"></article>'


def generated_pages(book: dict, photos: list[dict], base: str) -> list[str]:
    pages = [cover_page(book, book["cover_photo"], base), blank_page(), title_page(book)]
    index = 0
    for chapter in month_chapters(photos):
        year, month = chapter["key"]
        if len(chapter["photos"]) >= 4:
            pages.append(divider_page(month, year, len(chapter["photos"])))
        for photo in chapter["photos"]:
            pages.append(photo_page(book, photo, index, base))
            index += 1
    pages.append(colophon_page(book))
    if len(pages) % 2 == 0:
        pages.append(blank_page())
    pages.append(back_cover(book))
    return pages


def book_html(book: dict, pages: list[str], base: str) -> str:
    pages = [page.replace("<img ", '<img draggable="false" ') for page in pages]
    body = "\n\n".join("        " + page.replace("\n", "\n        ") for page in pages)
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{esc(book["title"])} · 照片 {book["year"]}</title>
  <link rel="stylesheet" href="{base}shared/styles.css">
</head>
<body>
<main class="room">
  <header class="book-header">
    <a href="{base}index.html">← 全部图册</a><h1>{esc(book["title"])}</h1><span id="orientation">双页展开</span>
  </header>
  <section class="stage" aria-label="可以翻页的照片书">
    <div class="book-rig">
      <div id="book" class="book" data-page-width="{PAGE_W}" data-page-height="{PAGE_H}" style="--cloth:{esc(book["cloth"])}">
{body}
      </div>
    </div>
  </section>
  <footer class="controls" aria-label="翻页控制">
    <button id="previous" type="button" aria-label="上一页">←</button>
    <div class="status" aria-live="polite"><span id="page-status">封面</span><small>拖动，或使用方向键</small></div>
    <button id="next" type="button" aria-label="下一页">→</button>
  </footer>
</main>
<script src="{base}shared/vendor/page-flip.browser.js"></script>
<script src="{base}shared/flipbook.js"></script>
</body>
</html>
'''


def curated_pages(path: str, base: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        body = handle.read()
    body = body.replace("{{base}}", base)
    return re.findall(r"<article\b.*?</article>", body, re.S)


def library_html(books: list[dict]) -> str:
    cards = []
    for book in books:
        cards.append(f'''      <a class="book-card" href="books/{book["year"]}/">
        <span class="card-cover" style="--cloth:{esc(book["cloth"])}">
          <span class="card-year">{book["year"]}</span>
          <span class="card-title">{esc(book["title"])}</span>
          <img class="card-photo" src="assets/photos/{book["year"]}/{book["cover_photo"]["file"]}" alt="" loading="lazy" draggable="false">
        </span>
        <span class="card-info"><b>{book["count"]}</b> 张 · {esc(book["range"])}</span>
      </a>''')
    total = sum(book["count"] for book in books)
    years = sorted(book["year"] for book in books)
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>照片 · {years[0]}—{years[-1]}</title>
  <link rel="stylesheet" href="library.css">
</head>
<body>
<main class="library">
  <header class="library-head">
    <p class="eyebrow">照片</p>
    <h1>{years[0]} — {years[-1]}</h1>
    <p class="meta">{len(books)} 本图册 · {total} 张照片</p>
  </header>
  <section class="shelf" aria-label="图册列表">
{os.linesep.join(cards)}
  </section>
  <footer class="library-foot">选一本，翻页阅读。</footer>
</main>
</body>
</html>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photo", default=os.path.join(ROOT, "photo"))
    parser.add_argument("--out", default=ROOT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    photo_root = os.path.abspath(args.photo)
    out_root = os.path.abspath(args.out)
    with open(os.path.join(ROOT, "books.json"), encoding="utf-8") as handle:
        config = json.load(handle)

    books = []
    for entry in config["books"]:
        year = str(entry["year"])
        year_dir = os.path.join(photo_root, year)
        if not os.path.isdir(year_dir):
            print(f"skip {year}: {year_dir} not found")
            continue
        photos = collect(year_dir, os.path.join(out_root, "assets", "photos", year), args.force, write=not entry.get("curated"))
        if not photos:
            continue
        skipped = 0
        if not entry.get("curated") and entry.get("dedupe", True):
            photos, skipped = drop_bursts(photos)
        cover = pick_cover(photos, entry.get("cover", ""))
        if entry.get("curated") and entry.get("cover"):
            cover = {"file": entry["cover"]}
        book = {
            "year": year,
            "title": entry["title"],
            "cloth": entry.get("cloth", "#2f3d40"),
            "count": len(photos),
            "skipped": skipped,
            "range": date_range(photos),
            "subtitle": date_range(photos),
            "cover_photo": cover,
        }
        base = "../" * (len(os.path.relpath(os.path.join(out_root, "books", year), out_root).split(os.sep)))
        if entry.get("curated"):
            pages = curated_pages(os.path.join(ROOT, entry["curated"]), base)
        else:
            pages = generated_pages(book, photos, base)
        book_dir = os.path.join(out_root, "books", year)
        os.makedirs(book_dir, exist_ok=True)
        with open(os.path.join(book_dir, "index.html"), "w", encoding="utf-8") as handle:
            handle.write(book_html(book, pages, base))
        books.append(book)
        print(f"{year}: {len(photos):3d} photos, {len(pages):3d} pages, cover {cover['file']}")

    books.sort(key=lambda b: b["year"], reverse=True)
    with open(os.path.join(out_root, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(library_html(books))
    os.makedirs(os.path.join(out_root, "data"), exist_ok=True)
    with open(os.path.join(out_root, "data", "books.json"), "w", encoding="utf-8") as handle:
        json.dump([{k: v for k, v in b.items() if k != "cover_photo"} for b in books], handle, ensure_ascii=False, indent=2)
    print(f"library: {len(books)} books")
    return 0


if __name__ == "__main__":
    sys.exit(main())
