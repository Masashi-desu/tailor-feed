#!/usr/bin/env python3
"""Duplicate detection helpers shared by collect.py / build_html.py, plus a one-shot re-processor.
canon_key = 'u:' + normalized URL (aggregator links resolved to the original article when possible).
Fallback: normalized title ('t:' key) matched within TITLE_WINDOW_DAYS."""
import re, sqlite3, sys, unicodedata, os
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import settings

TITLE_WINDOW_DAYS = 3
TRACK = re.compile(r"^(utm_.*|ref|ref_src|fbclid|gclid|mc_cid|mc_eid|cmpid|ocid|taid|guccounter|smid|sr_share|oc|__twitter_impression|rss|feed|src)$", re.I)
SUFFIX = re.compile(r"\s+[-–—|｜:：]\s*[^-–—|｜]{1,40}$")

def norm_url(u):
    """Canonical comparison form: https, no www, no AMP, no tracking params/fragment, no trailing slash."""
    u = (u or "").strip()
    try: p = urlsplit(u)
    except ValueError: return u.lower()
    host = (p.hostname or "").lower()
    if host.startswith("www."): host = host[4:]
    if host.startswith("amp."): host = host[4:]
    if host.startswith("m.") and host.count(".") >= 2: host = host[2:]
    path = re.sub(r"/amp/?$|/amp(?=/)|\.amp(?=\.html?$)", "", p.path or "/")
    path = re.sub(r"/+$", "", path) or "/"
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACK.match(k) and k.lower() not in ("amp", "outputtype")]
    if settings.AGG_HOST and host.endswith(settings.AGG_HOST): q = []
    return urlunsplit(("https", host, path, urlencode(sorted(q)), ""))

def is_agg(u): return settings.is_agg(u)

def norm_title(t, source=""):
    t = unicodedata.normalize("NFKC", t or "").lower().strip()
    src = re.sub(r"\s*\(via [^()]*\)$", "", (source or "").lower()).strip()
    for _ in range(2):  # strip trailing ' - Site Name', ' | Site', etc.
        m = SUFFIX.search(t)
        if not m: break
        tail = re.sub(r"^\W+", "", m.group(0)).strip()
        # strip if it names the source, or is short site-ish (<=4 words) and looks like a brand
        if (src and (tail in src or src.split()[0] in tail)) or len(tail.split()) <= 4 and len(t) - len(m.group(0)) >= 15:
            t = t[:m.start()]
        else: break
    t = re.sub(r"\s*\([^()]{1,30}\)\s*$", "", t)  # trailing '(Publisher Name)' credit (syndicated copies)
    t = re.sub(r"[\W_]+", "", t)  # strip punctuation/spaces (keeps CJK letters)
    return t

def url_key(url, orig=None):
    return "u:" + norm_url(orig or url)

def migrate(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(news)")}
    for c in ("canon_key", "orig_url", "title_key", "og_image"):
        if c not in cols: con.execute(f"ALTER TABLE news ADD COLUMN {c} TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_canon ON news(canon_key)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_tkey ON news(title_key)")
    con.commit()

def find_existing(con, ckey, tkey, pub, exclude_id=None):
    """Return id of an existing row that duplicates (ckey, tkey near pub), else None."""
    r = con.execute("SELECT id FROM news WHERE canon_key=? AND id IS NOT ? LIMIT 1", (ckey, exclude_id)).fetchone()
    if r: return r[0]
    if tkey and len(tkey) >= 8:
        d = datetime.fromisoformat(pub)
        lo, hi = (d - timedelta(days=TITLE_WINDOW_DAYS)).isoformat(), (d + timedelta(days=TITLE_WINDOW_DAYS)).isoformat()
        r = con.execute("SELECT id FROM news WHERE title_key=? AND published_at BETWEEN ? AND ? AND id IS NOT ? ORDER BY id LIMIT 1",
                        (tkey, lo, hi, exclude_id)).fetchone()
        if r: return r[0]
    return None

def _merge_tags(*tagstrs):
    out = []
    for s in tagstrs:
        for x in (s or "").split(","):
            if x and x not in out: out.append(x)
    return ",".join(out)

def merge_into(con, keep_id, drop):
    """Merge row dict `drop` (or incoming item) into keep_id: og_image, on_board, categories(tags 'cat:<c>')."""
    k = con.execute("SELECT category,tags,og_image,on_board,url,source,title,summary FROM news WHERE id=?", (keep_id,)).fetchone()
    cat, tags, og, ob, url, src, title, summ = k
    extra = []
    if drop.get("category") and drop["category"] != cat: extra.append("cat:" + drop["category"])
    for x in (drop.get("tags") or "").split(","):
        if x.startswith("cat:") and x != "cat:" + cat: extra.append(x)
    newtags = _merge_tags(tags, drop.get("tags"), ",".join(extra))
    newtags = ",".join(x for x in newtags.split(",") if x != "cat:" + cat)
    # prefer original source over aggregator: swap visible fields if keep is GN and drop is not
    if is_agg(url) and drop.get("url") and not is_agg(drop["url"]):
        con.execute("UPDATE news SET url=?||'#tmp', source=?, title=?, summary=COALESCE(NULLIF(?,''),summary) WHERE id=?",
                    (drop["url"], drop["source"], drop["title"], drop.get("summary") or "", keep_id))
    img = None
    if not og and drop.get("og_image"):  # og files are named by row id; move it so fetch_og cleanup keeps it
        pub = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
        src_f = os.path.join(pub, drop["og_image"]); img = f"og/{keep_id}{os.path.splitext(drop['og_image'])[1]}"
        if os.path.exists(src_f): os.replace(src_f, os.path.join(pub, img))
        else: img = None
    con.execute("UPDATE news SET tags=?, og_image=COALESCE(og_image,?), on_board=MAX(on_board,?) WHERE id=?",
                (newtags, img, drop.get("on_board") or 0, keep_id))

def rank(r):
    """Lower = better to keep: original source, has image, on_board, earliest id."""
    return (is_agg(r["url"]), not r["og_image"], -(r["on_board"] or 0), r["id"])

def reprocess(db, resolve=True):
    """Fill keys for all rows (resolving aggregator URLs) and merge duplicates. Returns stats by cause."""
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row; migrate(con)
    rows = [dict(r) for r in con.execute("SELECT * FROM news ORDER BY id")]
    if resolve:
        todo = [r for r in rows if is_agg(r["url"]) and not r["orig_url"]]
        if todo:
            import httpx
            from concurrent.futures import ThreadPoolExecutor
            from fetch_og import agg_resolve, UA
            def res(r):
                try:
                    with httpx.Client(headers=UA, timeout=10, follow_redirects=True) as cl:
                        return r["id"], agg_resolve(cl, r["url"])
                except Exception: return r["id"], None
            with ThreadPoolExecutor(8) as ex:
                got = dict(ex.map(res, todo))
            for r in todo:
                if got.get(r["id"]): r["orig_url"] = got[r["id"]]
            print(f"resolved {sum(1 for v in got.values() if v)}/{len(todo)} aggregator links", file=sys.stderr)
    for r in rows:
        r["canon_key"] = url_key(r["url"], r["orig_url"]); r["title_key"] = norm_title(r["title"], r["source"])
        con.execute("UPDATE news SET canon_key=?, orig_url=?, title_key=? WHERE id=?", (r["canon_key"], r["orig_url"], r["title_key"], r["id"]))
    # union-find groups
    par = {r["id"]: r["id"] for r in rows}; cause = {}
    def f(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    def u(a, b, why):
        ra, rb = f(a), f(b)
        if ra != rb: par[rb] = ra; cause[b] = why
    by = {}
    for r in rows:
        if r["canon_key"] in by:
            o = by[r["canon_key"]]
            if is_agg(r["url"]) or is_agg(o["url"]): why = "aggregator_vs_original"
            elif r["url"] == o["url"]: why = "exact_url"
            elif r["source"] != o["source"]: why = "sibling_feed_url_variant" if r["source"].split()[0] == o["source"].split()[0] else "url_variant_cross_source"
            else: why = "url_variant"
            u(o["id"], r["id"], why)
        else: by[r["canon_key"]] = r
    for i, a in enumerate(rows):
        if len(a["title_key"]) < 8: continue
        da = datetime.fromisoformat(a["published_at"])
        for b in rows[i+1:]:
            if b["title_key"] == a["title_key"] and abs((datetime.fromisoformat(b["published_at"]) - da).days) <= TITLE_WINDOW_DAYS and f(a["id"]) != f(b["id"]):
                u(a["id"], b["id"], "same_title_aggregator" if is_agg(a["url"]) or is_agg(b["url"]) else
                  ("same_title_sibling_feed" if a["source"].split()[0] == b["source"].split()[0] else "same_title_other_source"))
    groups = {}
    for r in rows: groups.setdefault(f(r["id"]), []).append(r)
    stats, removed = {}, []
    for g in groups.values():
        if len(g) < 2: continue
        g.sort(key=rank); keep = g[0]
        for d in g[1:]:
            why = cause.get(d["id"]) or next((cause[x["id"]] for x in g if x["id"] in cause), "?")
            stats[why] = stats.get(why, 0) + 1
            removed.append((keep["id"], keep["source"], d["id"], d["source"], why, d["title"][:60]))
            merge_into(con, keep["id"], d)
            con.execute("DELETE FROM news WHERE id=?", (d["id"],))
            if d.get("og_image"):  # og file is named by id; keep file referenced only if keep row now uses it
                pass
        con.execute("UPDATE news SET url=REPLACE(url,'#tmp','') WHERE id=?", (keep["id"],))
        k = con.execute("SELECT url,orig_url FROM news WHERE id=?", (keep["id"],)).fetchone()
        con.execute("UPDATE news SET canon_key=? WHERE id=?", (url_key(k[0], k[1] if is_agg(k[0]) else None), keep["id"]))
    con.commit()
    return stats, removed

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    st, rm = reprocess(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "news.db"), resolve="--no-resolve" not in sys.argv)
    for x in rm: print(*x, sep=" | ")
    print("removed by cause:", st, "total", sum(st.values()))
