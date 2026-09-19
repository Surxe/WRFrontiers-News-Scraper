#!/usr/bin/env python3
"""Archive every article in the War Robots: Frontiers news feed.

Companion to snapshot.py. Where snapshot.py grabs the 3 latest into a per-day,
gitignored `data/` bucket, this builds a *single, committed, canonical archive*
of the whole catalog under `archive/` — one file per article, keyed by id — so
`git diff`/`git log -p archive/` becomes the record of how WRF edits posts over
time.

Same JSON API, standard library only:

    GET /api/news?page=N   -> paginated list  {data:[...12...], links, meta}
    GET /api/news/{id}     -> one article     {data:{... , content, alternates}}

Design choices (why this is safe to re-run and to diff):
  * One article == one id. The file is named `<id>-<slug>`, but if WRF renames
    the slug we delete the stale `<id>-*` files first, so there is never more
    than one payload per id (a rename shows up as a clean delete+add in git).
  * Per-article files are the *verbatim* API payload — no fetch timestamps or
    other run-varying fields injected — so a diff reflects only what WRF changed,
    never just that we re-ran.
  * `index.json` is a compact, deterministically sorted manifest (id, slug,
    title, url, published_at, category). It is *merged* with any existing index,
    so a partial run (e.g. --latest 7) adds/updates rows without dropping ones a
    previous full run recorded.

Outputs (all under --out, default ./archive):
    index.json                          manifest of all known articles
    json/<id>-<slug>.json               full article payload (verbatim)
    html/<id>-<slug>.content.html       just the `content` body (readable diffs)

Usage:
    python3 scripts/archive.py --latest 7     # 7 most recent (verification run)
    python3 scripts/archive.py                # entire catalog (all pages)
    python3 scripts/archive.py --refresh-index-only   # rebuild index, no bodies
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://warrobotsfrontiers.com"
LIST_PATH = "/api/news"
ARTICLE_PATH = "/api/news/{id}"
USER_AGENT = "wrf-news-research/1.0 (+https://github.com/Surxe/wrf-news-research)"
TIMEOUT = 30
SLEEP = 0.3  # polite delay between requests (seconds)

# Compact fields kept in index.json (a subset of the list payload).
INDEX_FIELDS = ("id", "title", "url", "published_at", "category_title")


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def slug_from_url(url: str, article_id: int) -> str:
    """Return the `<id>-<slug>` filename stem, falling back to the bare id."""
    m = re.search(r"/news/(\d+-[a-z0-9-]+)", url or "")
    return m.group(1) if m else str(article_id)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def iter_list_items(max_items: int | None):
    """Yield list items newest-first, walking pages until exhausted or max_items."""
    page = 1
    seen = 0
    while True:
        url = f"{BASE}{LIST_PATH}?page={page}"
        print(f"Fetching list page {page}: {url}")
        listing = fetch_json(url)
        items = listing.get("data", [])
        meta = listing.get("meta", {})
        last_page = meta.get("last_page")
        if page == 1:
            print(f"  catalog: {meta.get('total')} articles across {last_page} pages")
        for it in items:
            yield it
            seen += 1
            if max_items is not None and seen >= max_items:
                return
        if not items or (last_page is not None and page >= last_page):
            return
        page += 1
        time.sleep(SLEEP)


def prune_stale(json_dir: Path, html_dir: Path, aid, keep_stem: str) -> None:
    """Remove any prior files for this id whose slug differs from keep_stem."""
    for f in json_dir.glob(f"{aid}-*"):
        if f.name != f"{keep_stem}.json":
            f.unlink()
    for f in html_dir.glob(f"{aid}-*"):
        if f.name != f"{keep_stem}.content.html":
            f.unlink()
    # bare-id fallbacks from an earlier run
    if keep_stem != str(aid):
        (json_dir / f"{aid}.json").unlink(missing_ok=True)
        (html_dir / f"{aid}.content.html").unlink(missing_ok=True)


def load_index(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return {row["id"]: row for row in rows}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def save_index(path: Path, index: dict) -> None:
    rows = sorted(index.values(), key=lambda r: (-(r.get("published_at") or 0), r.get("id") or 0))
    write_json(path, rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive the full WRF news catalog to a committed dir.")
    ap.add_argument("--out", default="archive", type=Path, help="output directory (default: archive)")
    ap.add_argument("--latest", type=int, default=None,
                    help="only archive the N most recent articles (default: all)")
    ap.add_argument("--refresh-index-only", action="store_true",
                    help="rebuild index.json from list pages without fetching article bodies")
    args = ap.parse_args()

    out: Path = args.out
    json_dir = out / "json"
    html_dir = out / "html"
    out.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)

    index = load_index(out / "index.json")
    fetched = errors = 0

    try:
        for it in iter_list_items(args.latest):
            aid = it["id"]
            index[aid] = {k: it.get(k) for k in INDEX_FIELDS}

            if args.refresh_index_only:
                continue

            stem = slug_from_url(it.get("url", ""), aid)
            art_url = f"{BASE}{ARTICLE_PATH.format(id=aid)}"
            print(f"  article {aid}: {it.get('title', '')[:60]!r}")
            try:
                article = fetch_json(art_url)
            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                print(f"    ERROR fetching article {aid}: {e}", file=sys.stderr)
                errors += 1
                continue

            prune_stale(json_dir, html_dir, aid, stem)
            write_json(json_dir / f"{stem}.json", article)
            content = (article.get("data") or {}).get("content")
            if content is not None:
                (html_dir / f"{stem}.content.html").write_text(content, encoding="utf-8")
            fetched += 1
            time.sleep(SLEEP)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"ERROR fetching list: {e}", file=sys.stderr)
        save_index(out / "index.json", index)
        return 1

    save_index(out / "index.json", index)
    print(f"Done. index has {len(index)} articles; "
          f"fetched {fetched} bodies this run ({errors} errors). Output under {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
