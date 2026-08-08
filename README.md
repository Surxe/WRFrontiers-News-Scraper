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

1. Fetches `/api/news?page=1` → `news_list.json`.
2. Takes the **3 latest** items from that list and fetches each in full
   (`/api/news/{id}`), writing:
   - `articles/<id>-<slug>.json` — full article payload.
   - `articles/<id>-<slug>.content.html` — just the `content` body, so
     edits diff readably.

Output is **bucketed per day** under `data/<YYYY-MM-DD>/`. Re-running on the same
day **overwrites that day's files** (idempotent), so a repeated pull just
refreshes today's snapshot. A new day starts a fresh folder, so an article that
was edited/bumped between days is captured separately per pull-day.

`data/` is gitignored by default, so snapshots are local working output;
un-ignore it (edit `.gitignore`) if you want the day folders recorded in git.

```bash
python3 scripts/snapshot.py                    # -> data/<today>/
python3 scripts/snapshot.py --latest 5         # capture more articles
python3 scripts/snapshot.py --date 2026-08-08  # force a specific day folder
python3 scripts/snapshot.py --page 2           # snapshot an older list page

# Or the double-clickable wrapper (keeps the terminal open at the end):
scripts/run-snapshot.sh
```

### Desktop shortcut (KDE)

`scripts/wrf-news-snapshot.desktop` is a ready-made launcher that runs the
wrapper in a terminal. Install it for your user:

```bash
# Appears in the K menu / app launcher:
cp scripts/wrf-news-snapshot.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications 2>/dev/null || true

# ...and/or drop a clickable copy on the desktop:
mkdir -p ~/Desktop
cp scripts/wrf-news-snapshot.desktop ~/Desktop/
chmod +x ~/Desktop/wrf-news-snapshot.desktop   # KDE requires the exec bit
```

The first time you launch a desktop copy, KDE may ask you to **trust** it —
allow it once. To edit it in the GUI instead: right-click the desktop →
*Create New → Link to Application*, then point *Command* at
`scripts/run-snapshot.sh` and tick *Run in terminal* under the *Application* tab.

### Recommended cadence

Run on each in-game update (weekly, when the discount refreshes — Tuesdays
~10:00 CEST / 01:00 PT). If you un-ignore `data/`, committing after each run
captures every edit to the bumped articles in git history.

## Repository layout

```
wrf-news-research/
├── scripts/
│   ├── snapshot.py                # fetch news list + N latest articles
│   ├── run-snapshot.sh            # double-clickable wrapper (cd + run + pause)
│   └── wrf-news-snapshot.desktop  # KDE launcher (install to ~/.local/share/applications)
└── data/                          # gitignored; per-day snapshots
    └── <YYYY-MM-DD>/
        ├── news_list.json               # /api/news?page=1
        └── articles/
            ├── <id>-<slug>.json         # full article payload
            └── <id>-<slug>.content.html # article body HTML (readable diffs)
```
