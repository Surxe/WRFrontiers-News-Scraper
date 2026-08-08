# wrf-news-research

Research + tooling for tracking the [War Robots: Frontiers news feed](https://warrobotsfrontiers.com/en/news?category=all&page=1),
so we can see **how and when the WRF team edits news posts** — in particular the
recurring weekly **Intel & Salvage Discount** article, whose item list feeds
[WRFrontiers-Discount-Visualizer](https://github.com/Surxe/WRFrontiers-Discount-Visualizer).

## How the news page works

The site (`https://warrobotsfrontiers.com`) is a **Nuxt (Vue) SSR** frontend
served by nginx, but behind it is a clean **Laravel-style JSON API**. There's no
need to scrape rendered HTML — hit the API directly:

| Endpoint | Returns |
|---|---|
| `GET /api/news?page=N` | Paginated list: `{ data: [ …12 items… ], links, meta }`. `meta` = `current_page, last_page (25), per_page (12), total (292)`. Each item carries metadata (`id, title, summary, url, published_at, preview_image, full_image, category_*, meta_*, author, related_tags`) but **not** the body. |
| `GET /api/news/{id}` | One article: `{ data: { … } }`. Same fields **plus `content`** (full body HTML) and `alternates` (per-language URLs). `/api/news/{id}` and `/api/news/{id}-slug` are equivalent. |

`published_at` is a Unix timestamp (seconds, UTC).

### The "bump an old post" mechanism

The list is ordered by **`published_at` descending**. The WRF team does **not**
publish a fresh discount article each week — they **edit one recurring article in
place**:

- The **`id` and URL slug never change.** e.g. the discount article is `id=272`
  with slug `272-intel-salvage-discount-event-save-big-april-14-21` — the slug is
  a fossil of the *original* April post date.
- Each week they **rewrite the title/dates**, **prepend the new week's items**,
  and **bump `published_at`** to "now", so the same article re-surfaces on page 1.
- The discount items live in that article's `content` HTML as repeated blocks:
  `Featured Items (August 4–11)` → `War Robot Modules: …`, `Weapons: …`,
  `Gear: …`, with prior weeks accumulating underneath.

Because the id is stable, snapshotting the same article file each run gives a
readable diff of exactly what changed between snapshots. `data/` is **gitignored
by default** (see below) — un-ignore it if you want git to retain that edit
history via `git log -p data/`.

## Snapshot script

`scripts/snapshot.py` — standard library only, no dependencies.

Each run it:

1. Fetches `/api/news?page=1` → `data/news_list.json`.
2. Takes the **3 latest** items from that list and fetches each in full
   (`/api/news/{id}`), writing:
   - `data/articles/<id>-<slug>.json` — full article payload.
   - `data/articles/<id>-<slug>.content.html` — just the `content` body, so
     edits diff readably.

Files are **overwritten in place** each run. `data/` is gitignored by default,
so snapshots are local working output; un-ignore it (edit `.gitignore`) if you
want each run's changes recorded in git history.

```bash
python3 scripts/snapshot.py                 # page 1, 3 latest articles -> ./data
python3 scripts/snapshot.py --latest 5      # capture more articles
python3 scripts/snapshot.py --page 2 --out data/page2
```

### Recommended cadence

Run on each in-game update (weekly, when the discount refreshes — Tuesdays
~10:00 CEST / 01:00 PT). If you un-ignore `data/`, committing after each run
captures every edit to the bumped articles in git history.

## Repository layout

```
wrf-news-research/
├── scripts/
│   └── snapshot.py     # fetch news list + N latest articles into data/
└── data/
    ├── news_list.json               # /api/news?page=1
    └── articles/
        ├── <id>-<slug>.json         # full article payload
        └── <id>-<slug>.content.html # article body HTML (readable diffs)
```
