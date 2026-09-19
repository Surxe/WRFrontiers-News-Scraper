#!/usr/bin/env python3
"""Step 2 of the pipeline: detect a newly announced discount week and hand it to
the WRFrontiers-Discount-Visualizer.

Step 1 (archive.py --latest 3) has already scraped and persisted the latest posts
under archive/. This step is otherwise offline: it reads those persisted files,
identifies the discount post via the validated schedule-header signal (detect.py),
reduces the current week to a canonical id, and skips it if we've parsed it before.

On a genuinely new week it:
  * logs a `discount-announced` JSON event (-> journal),
  * dispatches the visualizer's `all.yml` GitHub Actions workflow with the
    as-announced item names + `MM-DD MM-DD` date range (the visualizer does its own
    name->game-id mapping), and
  * records the week id in the state file so it never re-dispatches.

Dispatch is OPT-IN: without --dispatch it prints the exact `gh` command it would
run (dry run), so the pipeline is safe to enable before you're ready to fire CI.

Exit status: 0 on a clean check (new week or not). Non-zero only on real errors,
so the systemd service is "failed" only when the check itself broke. Standard
library only (plus the `gh` CLI for the dispatch).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
VIS_REPO = "Surxe/WRFrontiers-Discount-Visualizer"
VIS_WORKFLOW = "all.yml"


def slug_from_url(url: str, article_id) -> str:
    m = re.search(r"/news/(\d+-[a-z0-9-]+)", url or "")
    return m.group(1) if m else str(article_id)


def latest_discount_from_archive(archive: Path, n: int):
    """Return the newest discount article (data dict) among the n latest persisted
    posts, or None. Reads archive/index.json + archive/json/*.json — no network."""
    index_path = archive / "index.json"
    if not index_path.exists():
        print(f"ERROR: no index at {index_path}; run archive.py first", file=sys.stderr)
        return "no-index"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: bad index.json: {e}", file=sys.stderr)
        return "no-index"

    latest = sorted(index, key=lambda r: -(r.get("published_at") or 0))[:n]
    best = None
    for row in latest:
        stem = slug_from_url(row.get("url", ""), row.get("id"))
        jf = archive / "json" / f"{stem}.json"
        if not jf.exists():
            continue
        art = json.loads(jf.read_text(encoding="utf-8")).get("data") or {}
        if detect.is_discount(art.get("content") or ""):
            if best is None or (art.get("published_at") or 0) > (best.get("published_at") or 0):
                best = art
    return best


def dispatch_visualizer(items_csv: str, date_range: str, skip_deploy: bool, do_it: bool):
    """Fire (or print) the visualizer workflow_dispatch."""
    cmd = ["gh", "workflow", "run", VIS_WORKFLOW, "-R", VIS_REPO,
           "-f", f"items={items_csv}", "-f", f"target_date_range={date_range}",
           "-f", f"skip_deploy={'true' if skip_deploy else 'false'}"]
    if not do_it:
        print(json.dumps({"event": "dispatch-dry-run", "cmd": cmd}))
        return "dry-run"
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(json.dumps({"event": "dispatched", "repo": VIS_REPO, "workflow": VIS_WORKFLOW}))
        return "dispatched"
    except FileNotFoundError:
        print(json.dumps({"event": "dispatch-error", "error": "gh CLI not found"}))
        return "error"
    except subprocess.CalledProcessError as e:
        print(json.dumps({"event": "dispatch-error", "error": (e.stderr or "").strip()[:300]}))
        return "error"


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect a new WRF discount week and hand it to the visualizer.")
    ap.add_argument("--archive", type=Path, default=REPO / "archive",
                    help="archive dir produced by step 1 (default: archive)")
    ap.add_argument("--state", type=Path, default=REPO / "data" / "watch_state.json",
                    help="state file (default: data/watch_state.json, gitignored)")
    ap.add_argument("--latest", type=int, default=3,
                    help="how many latest persisted posts to check (default: 3)")
    ap.add_argument("--dispatch", action="store_true",
                    help="actually fire the visualizer workflow (default: dry-run). Can also be "
                         "enabled by setting WRF_DISPATCH=1 in the environment (used by the unit).")
    ap.add_argument("--prime", action="store_true",
                    help="record the current week as already-handled WITHOUT dispatching, so the "
                         "timer only fires on the next new week (use once at deploy time).")
    ap.add_argument("--skip-deploy", action="store_true",
                    help="pass skip_deploy=true to the visualizer (map only, no site deploy)")
    args = ap.parse_args()

    article = latest_discount_from_archive(args.archive, args.latest)
    if article == "no-index":
        return 1
    if not article:
        print(json.dumps({"event": "no-discount-post-found"}))
        return 0

    content = article.get("content") or ""
    week = detect.current_week(content)
    wid = detect.week_id(content, article.get("published_at"))
    dedup = wid or f"raw:{week}"

    args.state.parent.mkdir(parents=True, exist_ok=True)
    prev = {}
    if args.state.exists():
        try:
            prev = json.loads(args.state.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    parsed = list(prev.get("parsed_weeks", []))

    if dedup in parsed:
        print(json.dumps({"event": "no-change", "id": article["id"], "week_id": wid, "week": week}))
        return 0

    if args.prime:
        # Deploy-time seeding: mark the current week handled, dispatch nothing.
        parsed.append(dedup)
        args.state.write_text(json.dumps(
            {"parsed_weeks": parsed,
             "last": {"id": article["id"], "week_id": wid, "week": week,
                      "dispatched": "primed", "checked_at": int(time.time())}},
            indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"event": "primed", "id": article["id"], "week_id": wid, "week": week}))
        return 0

    # New week -> hand it to the visualizer.
    items = detect.discount_items(content)
    items_csv = ", ".join(items)
    date_range = detect.week_range_mmdd(content)

    event = {
        "event": "discount-announced",
        "id": article["id"], "title": article.get("title"), "url": article.get("url"),
        "week_id": wid, "week": week, "date_range": date_range,
        "items": items, "first_run": not prev,
    }
    if wid is None:
        event["warning"] = "could not parse a canonical week id"
    print(json.dumps(event, ensure_ascii=False))

    do_dispatch = args.dispatch or os.environ.get("WRF_DISPATCH") == "1"
    dispatched = "skipped"
    if date_range and items_csv:
        dispatched = dispatch_visualizer(items_csv, date_range, args.skip_deploy, do_dispatch)
    else:
        print(json.dumps({"event": "dispatch-skipped",
                          "reason": "missing date_range or items", "date_range": date_range}))

    # Only mark the week parsed once it's actually been handed off, so a dry-run or
    # a failed dispatch is retried on the next run rather than silently swallowed.
    if dispatched == "dispatched":
        parsed.append(dedup)
    state = {"parsed_weeks": parsed,
             "last": {"id": article["id"], "week_id": wid, "week": week,
                      "date_range": date_range, "dispatched": dispatched,
                      "checked_at": int(time.time())}}
    args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
