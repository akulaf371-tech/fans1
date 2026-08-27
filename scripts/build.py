"""Сборка статического блога FANS1 из content/posts.json + шаблонов."""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin"))
from md import excerpt_of  # noqa: E402

SITE = ROOT / "_site"
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

YT_RE = re.compile(r"(?:youtube\.com/(?:watch\?.*v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,})")


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


def fmt_msk(s: str) -> str:
    """«27 августа 2026 в 18:42» (московское время)."""
    try:
        d = parse_date(s).astimezone(ZoneInfo("Europe/Moscow"))
        return "%d %s %d в %02d:%02d" % (d.day, MONTHS_RU[d.month - 1],
                                         d.year, d.hour, d.minute)
    except Exception:
        return s


def sort_key(p: dict):
    return parse_date(p.get("date", "")), p.get("id", "")


def find_youtube(text: str):
    m = YT_RE.search(text or "")
    return m.group(1) if m else None


def body_to_html(body: str) -> str:
    """Текст поста -> HTML: абзацы, **жирный**, *курсив*, [ссылки](…), авто-YT."""
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
        p = esc(block.strip().replace("\n", "<br>"))
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", p)
        p = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)",
                   r'<a href="\2" target="_blank" rel="noopener">\1</a>', p)
        out.append("<p>%s</p>" % p)
    return "\n".join(out)


# --------------------------------------------------------------------- лента
MAX_FEED_MEDIA = 4      # сколько медиа показывать прямо в ленте
LONG_TEXT = 340         # длиннее -> кнопка «Показать полностью…»


def feed_media_html(media: list) -> str:
    if not media:
        return ""
    shown = media[:MAX_FEED_MEDIA]
    extra = len(media) - len(shown)
    cells = []
    for i, m in enumerate(shown):
        ex_attr = (' data-extra="+%d"' % extra) if (extra and i == len(shown) - 1) else ""
        u = esc(m["url"])
        if m["type"] == "video":
            cells.append('<figure class="mc"%s><video controls playsinline '
                         'preload="metadata" src="%s"></video></figure>' % (ex_attr, u))
        else:
            cells.append('<figure class="mc"%s><img loading="lazy" src="%s" alt="">'
                         "</figure>" % (ex_attr, u))
    return '<div class="fmedia m%d">%s</div>' % (len(shown), "".join(cells))


def feed_item(p: dict) -> str:
    slug = esc(p["slug"])
    plain_len = len(excerpt_of(p.get("body", "")))
    has_more = plain_len > LONG_TEXT
    media = p.get("media") or []
    tags = "".join('<span class="tag">#%s</span>' % esc(t) for t in p.get("tags", []))

    return (
        '<article class="feed-item">'
        '<div class="fhead">'
        '<img class="ava" src="/assets/favicon.svg" alt="">'
        '<div><div class="fname">FANS1</div>'
        '<div class="ftime">%s%s</div></div>'
        '<a class="flnk" href="/post/%s/">пост ↗</a>'
        '</div>'
        '<h2 class="feed-title"><a href="/post/%s/">%s</a></h2>'
        '<div class="ftextwrap%s">'
        '<div class="feed-text">%s</div>'
        '%s'
        '</div>'
        '%s'
        '<div class="ftags">%s</div>'
        '<div class="ffoot">'
        '<a class="ff-lnk" href="/post/%s/">Читать полностью →</a>'
        '<button class="ff-share" type="button" data-url="/post/%s/" onclick="f1Share(this)">🔗 Ссылка</button>'
        '</div>'
        '</article>'
        % (
            esc(fmt_msk(p.get("date", ""))),
            (" · 🎬 %d" % len(media)) if media else "",
            slug,
            slug,
            esc(p.get("title", "")),
            " has-more" if has_more else "",
            body_to_html(p.get("body", "")),
            ('<button class="show-more" type="button" onclick="f1Expand(this)">'
             "Показать полностью…</button>") if has_more else "",
            feed_media_html(media),
            tags,
            slug,
            slug,
        )
    )


def build_index(posts: list) -> None:
    tpl = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    ordered = sorted(posts, key=sort_key, reverse=True)   # сверху НОВОЕ, снизу старое
    if ordered:
        posts_html = '<section class="feed">%s</section>' % "\n".join(
            feed_item(p) for p in ordered)
    else:
        posts_html = ('<div class="empty-global">Постов пока нет 🏎️ '
                      "Зайдите в админку и напишите первый!</div>")
    out = (
        tpl.replace("@PAGE_TITLE@", "FANS1 — фанатский блог о Формуле-1")
        .replace("@HEADING_BLOCK@", "")
        .replace("@META_DESCRIPTION@", "Личный фанатский блог о Формуле-1: гонки, команды, драйверы.")
        .replace("@OG_IMAGE@", "")
        .replace("@POSTS@", posts_html)
    )
    (SITE / "index.html").write_text(out, encoding="utf-8")


# --------------------------------------------------------------- стр. поста
def media_html(m: dict, cls: str = "") -> str:
    u = esc(m["url"])
    if m["type"] == "video":
        return ('<figure class="%s"><video controls playsinline preload="metadata"'
                ' src="%s"></video></figure>' % (cls, u))
    return ('<figure class="%s"><a href="%s" target="_blank" rel="noopener">'
            '<img loading="lazy" src="%s" alt=""></a></figure>' % (cls, u, u))


def img_from(m: dict) -> str:
    return esc(m["url"]) if m["type"] == "image" else ""


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
    og_image = ((img_from(media[0]) if media else "")
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
            % (esc(p.get("title", "")), link, esc(p["id"]), rfc,
               esc(excerpt_of(p.get("body", ""))[:300]))
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
    print("[build] страниц: 1 главная (лента) + %d постов + rss | всего постов: %d"
          % (ok, len(posts)))


if __name__ == "__main__":
    main()
