"""
news_corroboration.py — soft corroborating evidence for pending incident
clusters, pulled from live Ghanaian news RSS feeds.

Per the "evidence fusion" discussion (project chat history, re: a district
officer verifying numerous reports): a news article matching a cluster's
location is CONTEXT for the officer, not a verification signal by itself.
It never changes a report's status -- it's surfaced the same way the
existing static zone score already is (see
govt_verification_sandbox._render_report_card), as one more thing worth
the officer's attention, not an automated confirmation.

Source selection, checked empirically rather than assumed (2026-10-04):
  * MyJoyOnline (myjoyonline.com/feed/) and 3News (3news.com/feed/) both
    return a live, currently-updating RSS feed (same-day entries).
  * The sources historical_flood_events.json cites for PAST events --
    Ghana News Agency, Citi Newsroom, GhanaWeb, floodlist.com -- were
    checked too and none currently serve a usable live feed: GNA's and
    Citi's /feed/ paths 301-redirect to their homepage (no RSS endpoint
    found), GhanaWeb has no discoverable RSS path, and floodlist.com's
    feed (both global and its Ghana tag) is reachable but its most recent
    entry predates this implementation by well over a year -- effectively
    inactive, not a live source. Re-check periodically; any of these could
    start working again and would be a straightforward addition to FEEDS.

Matching is a soft, approximate string match -- place-name tokens against
article title/description, not a geocoder. Treat a hit as "worth a human's
attention," never as confirmation of anything.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests
import streamlit as st

FEEDS = [
    {"name": "MyJoyOnline", "url": "https://www.myjoyonline.com/feed/"},
    {"name": "3News", "url": "https://3news.com/feed/"},
]

FLOOD_KEYWORDS = (
    "flood", "flooding", "floods", "flooded", "inundat", "downpour",
    "deluge", "waterlog", "submerge", "overflow", "drainage", "gutter",
)

# Generic admin-boundary words dropped so e.g. "Ablekuma Central Municipal"
# contributes place terms {"ablekuma", "central"}, not "municipal"/"district".
_STOPWORDS = {
    "municipal", "municipality", "metropolitan", "metropolis", "assembly",
    "district", "ext", "lower", "volta", "the", "and", "near",
}


def _place_terms(*texts: str | None) -> set[str]:
    """Place-name-ish tokens worth matching against a news article, pulled
    from a cluster's district name and its reports' location labels."""
    terms = set()
    for text in texts:
        if not text:
            continue
        for word in re.findall(r"[a-zA-Z]+", text.lower()):
            if len(word) >= 4 and word not in _STOPWORDS:
                terms.add(word)
    return terms


@st.cache_data(ttl=1800)
def fetch_flood_news(hours: int = 72) -> list[dict]:
    """Recent (last `hours`) flood-related items across FEEDS, newest
    first. Each feed is fetched and parsed independently so one
    unreachable or malformed feed never blocks the others -- if both fail
    (offline demo, network block, a feed going dark like floodlist.com
    did), this just returns an empty list; the cluster UI treats that as
    "no corroboration found," not an error."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for feed in FEEDS:
        try:
            resp = requests.get(
                feed["url"], headers={"User-Agent": "ThirdWave-streamlit-poc/1.0"}, timeout=10,
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
    return sorted(items, key=lambda x: x["published"], reverse=True)


def corroborating_news(news: list[dict], *location_texts: str | None, max_items: int = 3) -> list[dict]:
    """Items from `news` that share a place-name token with
    `location_texts` (typically a cluster's district plus its reports'
    location labels) -- a soft match, see module docstring."""
    terms = _place_terms(*location_texts)
    if not terms:
        return []
    hits = [item for item in news if any(term in item["title"].lower() for term in terms)]
    return hits[:max_items]
