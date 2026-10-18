"""Config loader. Custom files (gitignored) live in config/: feeds.json, settings.json.
Public examples: config/feeds.example.json, config/settings.example.json (format reference only, never loaded)."""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "config")

def _load(name, default):
    p = os.path.join(CONFIG, name)
    if not os.path.exists(p): return default
    with open(p, encoding="utf-8") as fh:
        txt = fh.read().strip()
    return json.loads(txt) if txt else default

def feeds():
    """List of (source, category, url) from config/feeds.json; [] if missing/empty."""
    return [tuple(x) for x in (_load("feeds.json", []) or [])]

_S = _load("settings.json", {}) or {}

# [[key, label, color], ...]; empty -> categories found in the DB, labelled by key.
CATEGORIES = [tuple(c) for c in _S.get("categories", [])]
HOT_TAGS = _S.get("hot_tags", [])
TAG_CATEGORIES = set(_S.get("tag_categories", []))
TAG_RULES = _S.get("tag_rules", {})
# News aggregator whose links wrap the original article (optional).
_AGG = _S.get("aggregator") or {}
AGG_HOST = (_AGG.get("host") or "").lower()          # e.g. "news.aggregator.example" (reserved .example TLD)
AGG_SOURCE_PREFIX = _AGG.get("source_prefix") or ""   # feed names starting with this are aggregator feeds
AGG_VIA_LABEL = _AGG.get("via_label") or "via aggregator"  # stored as "<site> (<via_label>)"

def is_agg(u):
    return bool(AGG_HOST) and AGG_HOST in (u or "").lower()
