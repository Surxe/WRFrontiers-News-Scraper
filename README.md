# WRFrontiers-News-Scraper

Scrapes the [War Robots: Frontiers news feed](https://warrobotsfrontiers.com/en/news)
and, when a new **weekly Intel & Salvage discount** is announced, hands it to
[WRFrontiers-Discount-Visualizer](https://github.com/Surxe/WRFrontiers-Discount-Visualizer).

The site is a Nuxt (Vue) SSR frontend over a clean JSON API, so we hit the API
directly instead of scraping HTML:

| Endpoint | Returns |
|---|---|
| `GET /api/news?page=N` | Paginated list (12/page, `meta.last_page` ~25). Metadata only, no body. |
| `GET /api/news/{id}` | One article incl. `content` (full body HTML). |

## The pipeline (two steps)

Run on a schedule (systemd timer on the home server — see
[`docs/HOME-SERVER-HANDOFF.md`](docs/HOME-SERVER-HANDOFF.md)):

1. **Scrape** — `archive.py --latest 3` fetches the 3 latest posts and persists
   each (payload + body) into the committed `archive/`.
2. **Detect + dispatch** — `watch_discount.py` reads those persisted posts,
   identifies the discount post, reduces its current week to a canonical id, and
   — if that week is new — dispatches the visualizer's `all.yml` workflow with the
   as-announced item names + `MM-DD MM-DD` date range. The visualizer does its own
   name→game-id mapping. (A future PR may add an LLM name-resolution step.)

### How the discount post is identified

Not by id, title, or category — those drift or leak. The reliable, format- and
id-agnostic signal (validated against the full 298-article archive: 2 hits, both
genuine, zero false positives) is the **dated discount-schedule header**:

```
<h2>Featured Items (September 15–22)</h2>      # current format
<h2>Upgrade Discounts (July 29–August 12)</h2> # older format
```

`detect.py` owns this signal and the week parsing. `python3 scripts/detect.py --verify`
re-checks it against `archive/` and prints what it finds.

### De-duplication by week

The current week is reduced to a canonical `YYYY-MM-DD` start date (the article
text has no year; it's inferred from `published_at`). `watch_discount.py` records
parsed weeks in its state file and never re-dispatches one — so extra polls and
catch-ups are free, and a week that resurfaces under a new post id is still
recognized as already-handled.

## Scripts

| Script | Role |
|---|---|
| `scripts/archive.py` | Scrape + persist. `--latest N` for the N newest, or all pages for a full catalog. Idempotent; verbatim payloads so `git diff archive/` shows only WRF's edits. |
| `scripts/detect.py` | The discount signal + week parsing (`is_discount`, `current_week`, `week_id`, `week_range_mmdd`, `discount_items`). `--verify` checks it against the archive. |
| `scripts/watch_discount.py` | Detect a new discount week from the archive and dispatch the visualizer (dry-run unless `--dispatch` / `WRF_DISPATCH=1`). |
| `scripts/snapshot.py` | Standalone per-day snapshot into gitignored `data/` (the original manual tool; kept for ad-hoc diffing). |

```bash
python3 scripts/archive.py --latest 3          # step 1
python3 scripts/watch_discount.py --latest 3   # step 2 (dry-run)
python3 scripts/watch_discount.py --dispatch   # step 2, actually fire the workflow
python3 scripts/detect.py --verify             # re-validate the signal
```

## Layout

```
WRFrontiers-News-Scraper/
├── scripts/         archive.py, detect.py, watch_discount.py, snapshot.py
├── archive/         committed catalog: index.json + json/ + html/
├── data/            gitignored: snapshot.py output + watch_state.json
├── assets/          launcher icon
└── docs/            HOME-SERVER-HANDOFF.md
```

`gh` (for the dispatch) is authenticated as the `dev` user on the home server.
