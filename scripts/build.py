"""Сборка статического блога FANS1 из content/posts.json + шаблонов."""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
from md import excerpt_of  # noqa: E402

SITE = ROOT / "_site"
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?.*v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,})")

FIG_CLOSE = "</figure>"


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def parse_date(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0)


def media_html(m: dict, cls: str = "") -> str:
    """HTML одного элемента медиа."""
    u = esc(m["url"])
    if m["type"] == "video":
        return (
            '<figure class="%s"><video controls playsinline preload="metadata"'
            ' src="%s"></video></figure>' % (cls, u)
        )
    return (
        '<figure class="%s"><a href="%s" target="_blank" rel="noopener">'
        '<img loading="lazy" src="%s" alt=""></a></figure>' % (cls, u, u)
    )


def find_youtube(text: str):
    m = YT_RE.search(text or "")
    return m.group(1) if m else None


def body_to_html(body: str) -> str:
    """Текст поста -> HTML: абзацы, мини-markdown (@@жирный@@, //курсив//), авто-YT."""
    out = []
    for block in re.split(r"\n\s*\n", (body or "").strip()):
        yt = find_youtube(block)
        if yt:
            out.append(
                '<figure class="embed-yt"><iframe loading="lazy" '
                'src="https://www.youtube-nocookie.com/embed/%s" title="YouTube видео" '
                'frameborder="0" allowfullscreen></iframe></figure>' % esc(yt)
            )
            continue
        p = block.strip().replace("\n", "<br>")
        p = esc(p)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", p)
        p = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', p)
        out.append("<p>%s</p>" % p)
    return "\n".join(out)


def img_from(m: dict) -> str:
    return esc(m["url"]) if m["type"] == "image" else ""


def sort_key(p: dict):
    return parse_date(p.get("date", "")), p.get("id", "")


def build_index(posts: list) -> None:
    tpl = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    cards = []
    for p in sorted(posts, key=sort_key, reverse=True):
        d = parse_date(p.get("date", ""))
        date_h = "%d %s %d" % (d.day, MONTHS_RU[d.month - 1], d.year) if d.year else ""
        excerpt = esc((excerpt_of(p.get("body", "")) or "")[:220])
        media = p.get("media") or []
        thumb = ""
        cls_extra = ""
        if media:
            m0 = media[0]
            if m0["type"] == "image":
                thumb = '<img loading="lazy" src="%s" alt="">' % esc(
                    m0["url"].replace("/upload/", "/upload/c_fill,w_900,h_506,q_auto/")
                )
            else:
                thumb = media_html({"url": m0["url"], "type": "video"}, "card__video")
                cls_extra = "has-video"
        else:
            thumb = '<div class="card__nomedia">&#127950;&#65039;</div>'
        tags = "".join('<a class="tag" href="#%s">#%s</a>' % (esc(t), esc(t)) for t in p.get("tags", []))
        cards.append(
            '<article class="card %s">'
            '<a class="card__thumb %s" href="/post/%s/" aria-label="%s">%s'
            '<span class="badge-badge">%d 📷</span></a>'
            '<div class="card__body"><time>%s</time>'
            '<h2 class="card__title"><a href="/post/%s/">%s</a></h2>'
            '<p class="card__excerpt">%s%s</p>'
            '<div class="tags">%s</div></div></article>'
            % (
                cls_extra,
                "" if media else "empty",
                esc(p["slug"]),
                esc(p.get("title", "")),
                thumb,
                len(media),
                date_h,
                esc(p["slug"]),
                esc(p.get("title", "")),
                excerpt,
                "&hellip;" if len(excerpt_of(p.get("body", ""))) > 220 else "",
                tags,
            )
        )
    posts_html = (
        '<div class="grid">' + "\n".join(cards) + "</div>"
        if cards
        else '<div class="empty">Постов пока нет 🏎️ Зайдите в админку и напишите первый!</div>'
    )
    out = (
        tpl.replace("@PAGE_TITLE@", "FANS1 — фанатский блог о Формуле-1")
        .replace("@HEADING@", "Лента")
        .replace("@META_DESCRIPTION@", "Личный фанатский блог о Формуле-1: гонки, команды, драйверы.")
        .replace("@OG_IMAGE@", "")
        .replace("@POSTS@", posts_html)
    )
    (SITE / "index.html").write_text(out, encoding="utf-8")


def build_post_page(p: dict) -> None:
    tpl = (ROOT / "templates" / "post.html").read_text(encoding="utf-8")
    d = parse_date(p.get("date", ""))
    date_h = "%d %s %d" % (d.day, MONTHS_RU[d.month - 1], d.year) if d.year else ""
    upd = p.get("updated")
    updated_h = ("<em>Обновлено: %d %s %d</em>" % (parse_date(upd).day,
                  MONTHS_RU[parse_date(upd).month - 1], parse_date(upd).year)) if upd else ""

    media = p.get("media") or []
    hero, gallery_parts = "", []
    if media:
        hero = media_html(media[0], "hero-item")
    for m in media[1:]:
        gallery_parts.append(media_html(m, "gal-item"))
    gallery = (
        '<button class="btn-media" type="button" onclick="f1ScrollToMedia()">📷 Медиа (%d)</button>'
        '<div class="grid-gallery" id="gallery">%s</div>' % (len(media), "".join(gallery_parts))
        if gallery_parts
        else ""
    )

    ytid = find_youtube(p.get("body", ""))
    hero_img = img_from(media[0]) if media else ""
    og_image = (img_from(media[0])
                or ("https://i.ytimg.com/vi/%s/hqdefault.jpg" % ytid if ytid else ""))

    out = (
        tpl.replace("@TITLE@", esc(p.get("title", "")))
        .replace("@EXCERPT@", esc(excerpt_of(p.get("body", ""))[:160]))
        .replace("@HERO_IMG@", og_image)
        .replace("@DATE_RU@", date_h)
        .replace("@HERO@", hero)
        .replace("@BODY@", body_to_html(p.get("body", "")))
        .replace("@GALLERY@", gallery)
        .replace("@UPDATED@", updated_h)
    )
    d_out = SITE / "post" / p["slug"]
    d_out.mkdir(parents=True, exist_ok=True)
    (d_out / "index.html").write_text(out, encoding="utf-8")


def build_rss(posts: list) -> None:
    items = []
    for p in sorted(posts, key=sort_key, reverse=True)[:20]:
        rfc = parse_date(p.get("date", "")).strftime("%a, %d %b %Y 12:00:00 +0000")
        link = "/post/%s/" % esc(p["slug"])
        items.append(
            "<item><title>%s</title><link>%s</link>"
            "<guid>%s</guid><pubDate>%s</pubDate>"
            "<description>%s</description></item>"
            % (esc(p.get("title", "")), link, esc(p["id"]), rfc, esc(excerpt_of(p.get("body", ""))[:300]))
        )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel><title>FANS1</title>'
        "<link>/</link><description>Фанатский блог о Формуле-1</description>"
        + "".join(items)
        + "</channel></rss>"
    )
    (SITE / "feed.xml").write_text(rss, encoding="utf-8")


def main():
    SITE.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "assets", SITE / "assets", dirs_exist_ok=True)
    # локально загруженные медиа тоже должны попасть на сайт
    pub_uploads = ROOT / "public" / "uploads"
    if pub_uploads.is_dir():
        shutil.copytree(pub_uploads, SITE / "uploads", dirs_exist_ok=True)

    posts = load_json(ROOT / "content" / "posts.json", [])
    for i, p in enumerate(posts):
        p.setdefault("tags", [])
        p.setdefault("media", [])
        p.setdefault("id", "post-%d" % i)

    build_index(posts)
    ok = 0
    for p in posts:
        try:
            build_post_page(p)
            ok += 1
        except Exception as e:
            print("  ! пропуск сломанного поста %s: %s" % (p.get("slug"), e))
    build_rss(posts)
    print("[build] страниц: 1 главная + %d постов + rss | всего постов в базе: %d" % (ok, len(posts)))


if __name__ == "__main__":
    main()
