# Tailor-feed

Personal news timeline: collects RSS/Atom feeds into SQLite, removes duplicate stories
(URL canonicalisation, optional news-aggregator link resolution, normalised-title matching), fetches OG images,
and builds a single static `public/index.html` with day/week navigation. The page loads Lucide
icons from a CDN and uses the local `public/favicon.svg`.

## Layout

| Path | Public (in git) | Notes |
|---|---|---|
| `collect.py`, `dedupe.py`, `fetch_og.py`, `build_html.py` | yes | pipeline |
| `run_daily.py` / `run_daily.ps1` | yes | runs collect → fetch_og → build |
| `serve.py` | yes | static server for `public/` (default `127.0.0.1:8095`) |
| `settings.py` | yes | config loader |
| `config/feeds.example.json`, `config/settings.example.json` | yes | format examples only (reserved example domains) |
| `public/favicon.svg` | yes | |
| `scripts/` | yes | Windows install (Startup shortcut + scheduled task) |
| `config/feeds.json` | **no** | your feed list `[[name, category, url], ...]` |
| `config/settings.json` | **no** | categories/colours, tag rules, hot tags, aggregator |
| `data/news.db` | **no** | collected articles |
| `public/og/`, `public/index.html` | **no** | image cache / generated page (embeds data) |
| `.env`, `logs/` | **no** | secrets / logs |

No feeds are bundled. Feeds are read only from `config/feeds.json`; if it is missing or empty,
`collect.py` prints `No feeds configured: copy config/feeds.example.json to config/feeds.json and edit it.`
and exits cleanly (the page still builds). `config/settings.json` is optional: without it, categories are
taken from the data, no tags are applied and aggregator handling is off.

`settings.json` keys: `categories` (`[key, label, colour]`), `hot_tags`, `tag_categories`,
`tag_rules` (`{tag: [regex, ...]}`), `aggregator` (`host`, `source_prefix`, `via_label`) — see the example file.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config\feeds.example.json config\feeds.json   # then replace with your feeds
copy config\settings.example.json config\settings.json  # optional
.venv\Scripts\python run_daily.py                   # creates data/news.db and public/index.html
.venv\Scripts\python serve.py --port 8095            # http://127.0.0.1:8095/
```

Linux/macOS: same, with `.venv/bin/python`.

## Windows resident setup (no admin)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1
```

Creates a Startup-folder shortcut that runs `serve.py` hidden at logon, and a per-user scheduled task
"Tailor-feed daily refresh" running `run_daily.ps1` every day at 07:00 (log: `logs\run_daily.log`).

The page uses only relative paths, so it can be served under a sub-path behind a reverse proxy, e.g. Caddy:

```
redir /tailor-feed /tailor-feed/ 308
handle_path /tailor-feed/* {
	reverse_proxy 127.0.0.1:8095
}
```

## Known limitations

`collect.py` removes tracking parameters with a legacy regular expression. If the first query parameter
is removed while another remains, the `?` can be lost (for example,
`https://example.com/story?utm_source=feed&id=42` becomes `https://example.com/story&id=42`).
This behaviour is retained to preserve URL and duplicate-key compatibility with existing databases;
correcting it requires a migration strategy for previously stored URLs and keys.

## License

MIT — see [LICENSE](LICENSE). Third-party dependencies retain their own licenses.
