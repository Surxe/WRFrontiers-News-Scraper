#!/usr/bin/env python3
"""Snapshot the War Robots: Frontiers news feed.

The public site (https://warrobotsfrontiers.com) is a Nuxt SSR frontend over a
Laravel-style JSON API. We snapshot that API rather than scraping HTML:

    GET /api/news?page=N   -> paginated list  {data:[...12...], links, meta}
                              list items carry metadata but NOT the body.
    GET /api/news/{id}     -> one article     {data:{... , content, alternates}}
                              `content` is the full body HTML.

The list is ordered by `published_at` descending. The WRF team recurringly
*edits an existing article in place* (id/slug unchanged), rewrites its title and
body, and bumps `published_at` so it re-surfaces on page 1 — this is how the
weekly discount post reappears. Because we overwrite the same files each run and
commit, `git log -p data/` becomes the change record: it shows exactly what they
edited between snapshots.

Outputs (all under --out, default ./data):
    news_list.json                 pretty-printed /api/news?page=1
    articles/<id>-<slug>.json      full article payload for the N latest
    articles/<id>-<slug>.content.html   just the `content` body (readable diffs)

No third-party dependencies — standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://warrobotsfrontiers.com"
LIST_PATH = "/api/news"
ARTICLE_PATH = "/api/news/{id}"
USER_AGENT = "wrf-news-research/1.0 (+https://github.com/Surxe/wrf-news-research)"
TIMEOUT = 30


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def slug_from_url(url: str, article_id: int) -> str:
    """Extract the `<id>-<slug>` tail from an article URL for a stable filename."""
    m = re.search(r"/news/(\d+-[a-z0-9-]+)", url or "")
    if m:
        return m.group(1)
    return str(article_id)


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot the WRF news feed to a data dir.")
    ap.add_argument("--out", default="data", type=Path, help="output directory (default: data)")
    ap.add_argument("--page", type=int, default=1, help="news list page to snapshot (default: 1)")
    ap.add_argument("--latest", type=int, default=3, help="number of latest articles to fetch in full (default: 3)")
    args = ap.parse_args()

    out: Path = args.out
    articles_dir = out / "articles"
    out.mkdir(parents=True, exist_ok=True)
    articles_dir.mkdir(parents=True, exist_ok=True)

    list_url = f"{BASE}{LIST_PATH}?page={args.page}"
    print(f"Fetching list: {list_url}")
    try:
        listing = fetch_json(list_url)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"ERROR fetching list: {e}", file=sys.stderr)
        return 1

    write_json(out / "news_list.json", listing)
    items = listing.get("data", [])
    meta = listing.get("meta", {})
    print(f"  list page {meta.get('current_page')}/{meta.get('last_page')} "
          f"({len(items)} items, {meta.get('total')} total)")

    latest = items[: args.latest]
    for it in latest:
        aid = it["id"]
        slug = slug_from_url(it.get("url", ""), aid)
        art_url = f"{BASE}{ARTICLE_PATH.format(id=aid)}"
        print(f"Fetching article {aid}: {it.get('title', '')[:60]!r}")
        try:
            article = fetch_json(art_url)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"  ERROR fetching article {aid}: {e}", file=sys.stderr)
            continue

        write_json(articles_dir / f"{slug}.json", article)
        content = (article.get("data") or {}).get("content")
        if content is not None:
            (articles_dir / f"{slug}.content.html").write_text(content, encoding="utf-8")

    print(f"Done. Snapshot written under {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
