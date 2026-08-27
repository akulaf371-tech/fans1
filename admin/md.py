"""Мини-хелперы для текста постов."""
import html
import re


def excerpt_of(body: str) -> str:
    t = re.sub(r"\s+", " ", (body or "").strip())
    t = re.sub(r"\*+|//|\[|\]\([^)]*\)|https?://\S+", "", t)
    return t.strip()


def fmt_date_ru(iso: str) -> str:
    MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    try:
        d = iso[:10].split("-")
        return "%s %s %s" % (int(d[2]), MONTHS[int(d[1]) - 1], d[0])
    except Exception:
        return iso


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", html.unescape(s or ""))
