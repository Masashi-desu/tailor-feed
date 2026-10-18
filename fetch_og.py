#!/usr/bin/env python3
"""Fetch og:image / twitter:image for recent articles, cache resized copies to public/og/<id>.<ext>.
Columns: og_image (local path 'og/<id>.webp' or NULL), og_checked_at (ISO). Failures retried after RETRY_DAYS."""
import json, os, re, sqlite3, sys, html as H
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import urljoin, urlparse, quote
import httpx
import settings
try:
    from PIL import Image
except ImportError:
    Image = None

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "news.db")
OGDIR = os.path.join(BASE, "public", "og")
DAYS, RETRY_DAYS, KEEP_DAYS, WORKERS, TIMEOUT, MAXW, MINW = 14, 3, 30, 8, 8, 800, 200
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
      "Accept-Language": "ja,en;q=0.8"}

def migrate(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(news)")}
    for c in ("og_image", "og_checked_at"):
        if c not in cols: con.execute(f"ALTER TABLE news ADD COLUMN {c} TEXT")
    con.commit()

def agg_resolve(cl, url):
    """Decode <aggregator>/rss/articles/<id> via its batchexecute endpoint. Returns URL or None."""
    if not settings.AGG_HOST: return None
    m = re.search(r"/articles/([^?/]+)", url)
    if not m: return None
    gid = m.group(1)
    r = cl.get(f"https://{settings.AGG_HOST}/articles/{gid}")
    sg = re.search(r'data-n-a-sg="([^"]+)"', r.text); ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
    if not (sg and ts): return None
    inner = json.dumps(["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
                        "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], gid, int(ts.group(1)), sg.group(1)])
    req = json.dumps([[["Fbv4je", inner, None, "generic"]]])
    r = cl.post(f"https://{settings.AGG_HOST}/_/DotsSplashUi/data/batchexecute",
                data={"f.req": req}, headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    m = re.search(r'garturlres\\",\\"(https?://[^\\"]+)', r.text)
    return m.group(1) if m else None

META = re.compile(r"<meta\b[^>]*>", re.I)
def find_og(page, base):
    found = {}
    for tag in META.findall(page[:400000]):
        k = re.search(r'(?:property|name)\s*=\s*["\']([^"\']+)', tag, re.I)
        v = re.search(r'content\s*=\s*["\']([^"\']*)', tag, re.I)
        if k and v and v.group(1).strip():
            found.setdefault(k.group(1).lower(), H.unescape(v.group(1).strip()))
    for k in ("og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        if k in found: return urljoin(base, found[k])
    return None

def save_image(cl, iid, img_url, referer):
    r = cl.get(img_url, headers={"Referer": referer}); r.raise_for_status()
    if len(r.content) < 1000: return None, "tiny bytes"
    if Image is None:
        ext = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(r.headers.get("content-type", "").split(";")[0], "jpg")
        rel = f"og/{iid}.{ext}"; open(os.path.join(BASE, "public", rel), "wb").write(r.content); return rel, None
    im = Image.open(BytesIO(r.content)); im.load()
    if im.width < MINW: return None, f"small {im.width}px"
    im = im.convert("RGB")
    if im.width > MAXW: im = im.resize((MAXW, round(im.height * MAXW / im.width)), Image.LANCZOS)
    rel = f"og/{iid}.webp"; im.save(os.path.join(BASE, "public", rel), "WEBP", quality=72, method=4)
    return rel, None

def work(row):
    iid, url, orig = row
    try:
        with httpx.Client(headers=UA, timeout=TIMEOUT, follow_redirects=True) as cl:
            if settings.AGG_HOST and urlparse(url).netloc.endswith(settings.AGG_HOST):
                real = orig or agg_resolve(cl, url)
                if not real: return iid, None, "aggregator unresolved"
                url = real
            r = cl.get(url)
            if r.status_code >= 400: return iid, None, f"HTTP {r.status_code}"
            if "html" not in r.headers.get("content-type", "html"): return iid, None, "not html"
            img = find_og(r.text, str(r.url))
            if not img: return iid, None, "no og:image"
            rel, err = save_image(cl, iid, img, str(r.url))
            return iid, rel, err
    except Exception as e:
        return iid, None, f"{type(e).__name__}: {str(e)[:80]}"

def cleanup(con):
    if not os.path.isdir(OGDIR): return 0
    keep = {f"{i}" for (i,) in con.execute("SELECT id FROM news WHERE published_at>=?",
            ((datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat(),))}
    n = 0
    for f in os.listdir(OGDIR):
        if f.split(".")[0] not in keep:
            os.remove(os.path.join(OGDIR, f)); n += 1
    con.execute("UPDATE news SET og_image=NULL WHERE published_at<?", ((datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat(),))
    con.commit(); return n

def main():
    os.makedirs(OGDIR, exist_ok=True)
    if not os.path.exists(DB): print("no database yet; skipping"); return
    con = sqlite3.connect(DB)
    if not con.execute("SELECT 1 FROM sqlite_master WHERE name='news'").fetchone(): print("no articles yet; skipping"); return
    migrate(con)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=DAYS)).isoformat(); retry = (now - timedelta(days=RETRY_DAYS)).isoformat()
    oc = "orig_url" if "orig_url" in {r[1] for r in con.execute("PRAGMA table_info(news)")} else "NULL"
    rows = con.execute(f"SELECT id,url,{oc} FROM news WHERE published_at>=? AND og_image IS NULL "
                       "AND (og_checked_at IS NULL OR og_checked_at<?)", (since, retry)).fetchall()
    print(f"checking {len(rows)} items"); ok = 0; reasons = {}
    with ThreadPoolExecutor(WORKERS) as ex:
        for iid, rel, err in ex.map(work, rows):
            con.execute("UPDATE news SET og_image=?, og_checked_at=? WHERE id=?", (rel, now.isoformat(timespec="seconds"), iid))
            if rel: ok += 1
            else:
                key = err.split(":")[0] if err else "?"; reasons[key] = reasons.get(key, 0) + 1
    con.commit()
    print(f"images: {ok}/{len(rows)}; failures: {reasons}; removed {cleanup(con)} stale cache files")

if __name__ == "__main__":
    main()
