"""
news_corroboration.py — backend port of streamlit_app/news_corroboration.py.
Same sources, same keyword/place-name matching logic (see that module's
docstring for why MyJoyOnline/3News and not the sources
historical_flood_events.json cites for past events -- GNA/Citi/GhanaWeb/
floodlist.com were checked and none currently serve a working live feed).

Duplicated rather than imported for the same reason as clustering.py: this
backend must stay runnable without a Streamlit dependency. st.cache_data's
TTL is replaced with a plain module-level cache keyed on `hours`, since
there's no Streamlit runtime to cache against here.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

FEEDS = [
    {"name": "MyJoyOnline", "url": "https://www.myjoyonline.com/feed/"},
    {"name": "3News", "url": "https://3news.com/feed/"},
]

FLOOD_KEYWORDS = (
    "flood", "flooding", "floods", "flooded", "inundat", "downpour",
    "deluge", "waterlog", "submerge", "overflow", "drainage", "gutter",
)

_STOPWORDS = {
    "municipal", "municipality", "metropolitan", "metropolis", "assembly",
    "district", "ext", "lower", "volta", "the", "and", "near",
}

_CACHE_TTL_S = 1800
_cache: dict[int, tuple[float, list[dict]]] = {}  # hours -> (fetched_at, items)


def _place_terms(*texts: str | None) -> set[str]:
    terms = set()
    for text in texts:
        if not text:
            continue
        for word in re.findall(r"[a-zA-Z]+", text.lower()):
            if len(word) >= 4 and word not in _STOPWORDS:
                terms.add(word)
    return terms


def fetch_flood_news(hours: int = 72) -> list[dict]:
    """Recent (last `hours`) flood-related items across FEEDS, newest
    first. Cached in-process for _CACHE_TTL_S so repeated requests within
    the same half hour don't re-hit the feeds. Each feed is fetched/parsed
    independently so one unreachable or malformed feed never blocks the
    other; if both fail this returns an empty list, not an error."""
    now = time.monotonic()
    cached = _cache.get(hours)
    if cached and (now - cached[0]) < _CACHE_TTL_S:
        return cached[1]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for feed in FEEDS:
        try:
            resp = requests.get(
                feed["url"], headers={"User-Agent": "ThirdWave-backend/1.0"}, timeout=10,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception:
            continue
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            desc = it.findtext("description") or ""
            pub_raw = it.findtext("pubDate")
            link = it.findtext("link")
            if not title or not pub_raw:
                continue
            try:
                pub = parsedate_to_datetime(pub_raw)
            except (TypeError, ValueError):
                continue
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub < cutoff:
                continue
            blob = f"{title} {desc}".lower()
            if not any(kw in blob for kw in FLOOD_KEYWORDS):
                continue
            items.append({"title": title, "link": link, "source": feed["name"], "published": pub})

    items.sort(key=lambda x: x["published"], reverse=True)
    _cache[hours] = (now, items)
    return items


def corroborating_news(news: list[dict], *location_texts: str | None, max_items: int = 3) -> list[dict]:
    terms = _place_terms(*location_texts)
    if not terms:
        return []
    hits = [item for item in news if any(term in item["title"].lower() for term in terms)]
    return hits[:max_items]
