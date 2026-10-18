#!/usr/bin/env python3
"""RSS/Atom collector -> SQLite (data/news.db). Idempotent (URL dedupe)."""
import calendar, html, json, re, sqlite3, sys, time, os
from datetime import datetime, timezone
import feedparser, httpx
import settings
import dedupe

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "news.db")
UA = {"User-Agent": "Mozilla/5.0 news-timeline/0.1 (personal)"}
MAX_PER_FEED = 40
SUMMARY_LEN = 160

TAG_RULES = settings.TAG_RULES  # {tag: [regex, ...]} from config/settings.json

from fetch_og import agg_resolve

def norm_url(u):
    u = re.sub(r"[?&](utm_[^=&]+|ref|fbclid)=[^&]*", "", u.strip())
    return u.rstrip("?&")

def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()

def make_summary(e):
    # No LLM API available: cleaned + truncated feed description.
    s = clean(e.get("summary") or e.get("description") or "")
    if s.startswith(clean(e.get("title", ""))[:30]) and len(s) < 200:  # aggregator: desc == title
        s = ""
    return s[:SUMMARY_LEN] + ("…" if len(s) > SUMMARY_LEN else "")

def tag(category, title, summary):
    if category not in settings.TAG_CATEGORIES:
        return []
    t = f"{title} {summary}"
    tags = [k for k, pats in TAG_RULES.items() if any(re.search(p, t, re.I) for p in pats)]
    if ("toolchanger" in tags or "multi-tool" in tags) and "cheap" in tags:
        tags.append("cheap-multitool")  # flag
    return tags

def init_db(con):
    con.execute("""CREATE TABLE IF NOT EXISTS news(
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
        source TEXT, category TEXT, published_at TEXT, fetched_at TEXT, summary TEXT,
        tags TEXT, on_board INTEGER NOT NULL DEFAULT 0)""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_pub ON news(published_at)")
    dedupe.migrate(con)

def load_feeds():
    """Feeds come only from config/feeds.json (gitignored). No built-in defaults."""
    return settings.feeds()

def main():
    feeds = load_feeds()
    if not feeds:
        print("No feeds configured: copy config/feeds.example.json to config/feeds.json and edit it.")
        return
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB); init_db(con)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = {}
    with httpx.Client(headers=UA, timeout=20, follow_redirects=True) as cl:
        for source, cat, url in feeds:
            try:
                for attempt in range(3):
                    try:
                        r = cl.get(url); r.raise_for_status(); break
                    except Exception:
                        if attempt == 2: raise
                        time.sleep(2)
                f = feedparser.parse(r.content)
            except Exception as ex:
                print(f"[WARN] {source}: {ex}", file=sys.stderr); continue
            new = 0
            for e in f.entries[:MAX_PER_FEED]:
                link = e.get("link"); title = clean(e.get("title"))
                if not link or not title: continue
                tp = e.get("published_parsed") or e.get("updated_parsed")
                pub = datetime.fromtimestamp(calendar.timegm(tp), timezone.utc).isoformat(timespec="seconds") if tp else now
                summ = make_summary(e)
                src = source
                if settings.AGG_SOURCE_PREFIX and source.startswith(settings.AGG_SOURCE_PREFIX) and e.get("source"):
                    src = f"{e.source.get('title','')} ({settings.AGG_VIA_LABEL})"
                url = norm_url(link); tags = ",".join(tag(cat, title, summ))
                old = con.execute("SELECT id FROM news WHERE url=?", (url,)).fetchone()
                orig = None
                if not old and dedupe.is_agg(url):
                    try: orig = agg_resolve(cl, url)
                    except Exception: orig = None
                ckey, tkey = dedupe.url_key(url, orig), dedupe.norm_title(title, src)
                dup = old[0] if old else dedupe.find_existing(con, ckey, tkey, pub)
                item = {"title": title, "url": url, "source": src, "category": cat, "summary": summ, "tags": tags}
                if dup:  # same story already stored: keep one row, merge category/tags (prefers original over aggregator)
                    dedupe.merge_into(con, dup, item)
                    con.execute("UPDATE news SET url=REPLACE(url,'#tmp','') WHERE id=?", (dup,))
                    if not dedupe.is_agg(url) and not old:
                        con.execute("UPDATE news SET canon_key=? WHERE id=? AND url=?", (ckey, dup, url))
                    continue
                cur = con.execute("INSERT OR IGNORE INTO news(title,url,source,category,published_at,fetched_at,summary,tags,canon_key,orig_url,title_key) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (title, url, src, cat, pub, now, summ, tags, ckey, orig, tkey))
                new += cur.rowcount
            stats[source] = new
            print(f"{source}: {len(f.entries)} entries, {new} new")
    con.commit()
    for c, n in con.execute("SELECT category,COUNT(*) FROM news GROUP BY category"):
        print(f"total {c}: {n}")

if __name__ == "__main__":
    main()
