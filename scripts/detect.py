#!/usr/bin/env python3
"""Identify War Robots: Frontiers *upgrade-discount* news posts and read their
current week — the single source of truth shared by the archiver and the watcher.

Why this signal (validated against the full 298-article archive, see --verify):

    The discount post is defined by its **schedule structure**, not its id, title,
    or category. Every genuine upgrade-discount post — and only those — contains a
    section header of the form:

        <h2>Featured Items (September 15-22)</h2>     # current format (id 272)
        <h2>Upgrade Discounts (July 29-August 12)</h2># older format  (id 251)

    Keying on that header:
      * survives the recurring in-place edits of id 272 (id/slug/title all drift),
      * survives WRF spinning up a brand-new post with a new id,
      * spans both known layouts, and
      * yields ZERO false positives: title/category are unreliable (28 EVENTS
        posts, 5 "discount" titles, Black-Friday promos) and the bare
        Modules/Weapons/Gear label triple leaks 10 patch-notes posts that reuse
        those labels for balance changes.

Public API:
    is_discount(content)   -> bool
    current_week(content)  -> str | None   # raw date range of the top block
    week_id(content, ts)   -> str | None   # canonical "YYYY-MM-DD" start-of-week key
    week_blocks(content)   -> list[(range, {category: [names]})]  # newest-first

The canonical week_id() is the dedup key: two snapshots of the same discount week
produce the same id regardless of en-dash/hyphen or cross-month text drift, so the
downstream parse pipeline can skip a week it has already processed. The article
text has no year, so it's inferred from `published_at` (the top block is always the
current week, so its start date is within days of publication).

Standard library only. Run `python3 scripts/detect.py --verify` to re-check the
signal against archive/ and print the identified discount posts.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone

_MONTHS = {}
for _i, _names in enumerate(
    [("January", "Jan"), ("February", "Feb"), ("March", "Mar"), ("April", "Apr"),
     ("May", "May"), ("June", "Jun"), ("July", "Jul"), ("August", "Aug"),
     ("September", "Sep", "Sept"), ("October", "Oct"), ("November", "Nov"),
     ("December", "Dec")], start=1):
    for _n in _names:
        _MONTHS[_n.lower()] = _i

# The left side of a range, e.g. "September 15" or "Sept 1", possibly "15 September".
_DAYMON_RE = re.compile(
    r"(?:(?P<m1>[A-Za-z]+)\s+(?P<d1>\d{1,2})|(?P<d2>\d{1,2})\s+(?P<m2>[A-Za-z]+))")
# Dash variants used between the two dates.
_DASH_RE = re.compile(r"\s*[‒–—―\-–—]\s*")

# A discount post is any article carrying a dated discount-schedule header.
# Broadened beyond the two seen phrasings with a couple of likely synonyms, but
# still anchored on "<phrase> (<something with a digit>)" so patch notes and
# promos can't match. Add phrasings here if WRF renames the section again.
_HEADER_PHRASES = r"Featured Items|Upgrade Discounts|Discount Schedule|Featured Discounts"
_HEADER_RE = re.compile(
    r"<h2>\s*(?:" + _HEADER_PHRASES + r")\s*\(([^)]*\d[^)]*)\)\s*</h2>",
    re.IGNORECASE,
)
_CATEGORY_LABELS = ("War Robot Modules", "Weapons", "Gear")


def is_discount(content: str) -> bool:
    """True if the article body is an upgrade-discount schedule post."""
    return bool(content) and _HEADER_RE.search(content) is not None


def week_blocks(content: str):
    """Return [(date_range, {label: [names]})] for each schedule block, newest-first.

    The WRF team prepends each new week's block to the top, so the first element
    is always the current week.
    """
    out = []
    # Split on the schedule headers, keeping the captured date range.
    parts = _HEADER_RE.split(content or "")
    # parts = [pre, range1, body1, range2, body2, ...]
    for i in range(1, len(parts), 2):
        rng = html.unescape(parts[i]).strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        cats = {}
        for label in _CATEGORY_LABELS:
            m = re.search(
                re.escape(label) + r"\s*:\s*(?:&nbsp;|\s)*</strong>\s*(?:&nbsp;)?\s*([^<]*)",
                body,
            )
            if m:
                names = [html.unescape(n).strip() for n in m.group(1).split(",") if n.strip()]
                cats[label] = names
        out.append((rng, cats))
    return out


def current_week(content: str):
    """Date-range string of the newest schedule block, or None."""
    blocks = week_blocks(content)
    return blocks[0][0] if blocks else None


def _range_start(rng: str):
    """Parse the (month, day) that a date-range string starts on, or None."""
    if not rng:
        return None
    left = _DASH_RE.split(rng, 1)[0].strip()
    m = _DAYMON_RE.search(left)
    if not m:
        return None
    mon = (m.group("m1") or m.group("m2") or "").lower()
    day = m.group("d1") or m.group("d2")
    if mon not in _MONTHS or not day:
        return None
    return _MONTHS[mon], int(day)


def week_id_from_range(rng: str, published_at=None):
    """Canonical 'YYYY-MM-DD' start date for a range string.

    The text carries no year, so it's taken from `published_at` (the current week
    starts within days of publication); the year is nudged by ±1 only if that would
    otherwise place the week half a year from publication (Dec/Jan boundary).
    """
    md = _range_start(rng)
    if md is None:
        return None
    month, day = md
    ref = (datetime.fromtimestamp(published_at, timezone.utc).date()
           if published_at else date.today())
    try:
        cand = date(ref.year, month, day)
    except ValueError:
        return None
    if (cand - ref).days > 180:
        cand = cand.replace(year=ref.year - 1)
    elif (ref - cand).days > 180:
        cand = cand.replace(year=ref.year + 1)
    return cand.isoformat()


def week_id(content: str, published_at=None):
    """Canonical dedup key for the current (newest) discount week, or None."""
    return week_id_from_range(current_week(content), published_at)


def _range_end(rng: str):
    """Parse the (month, day) a date-range ends on, or None."""
    if not rng:
        return None
    parts = _DASH_RE.split(rng, 1)
    if len(parts) < 2:
        return None
    right = parts[1].strip()
    m = _DAYMON_RE.search(right)
    if m:
        mon = (m.group("m1") or m.group("m2") or "").lower()
        day = m.group("d1") or m.group("d2")
        if mon in _MONTHS and day:
            return _MONTHS[mon], int(day)
    # Day-only right side ("September 15–22") inherits the start month.
    start = _range_start(rng)
    dm = re.search(r"\d{1,2}", right)
    if start and dm:
        return start[0], int(dm.group())
    return None


def week_range_mmdd(content: str):
    """The current week as the visualizer's 'MM-DD MM-DD' target_date_range, or None."""
    rng = current_week(content)
    start, end = _range_start(rng), _range_end(rng)
    if not start or not end:
        return None
    return f"{start[0]:02d}-{start[1]:02d} {end[0]:02d}-{end[1]:02d}"


def discount_items(content: str):
    """Flat list of the current week's discounted item names (modules, weapons, gear),
    in announcement order — the visualizer's `items` input (as-announced, unresolved)."""
    blocks = week_blocks(content)
    if not blocks:
        return []
    cats = blocks[0][1]
    out = []
    for label in _CATEGORY_LABELS:
        out.extend(cats.get(label, []))
    return out


def _verify() -> int:
    """Run the detector over archive/ and report the identified discount posts."""
    import glob
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "archive" / "json"
    hits = []
    for jf in sorted(glob.glob(str(root / "*.json"))):
        a = json.load(open(jf))["data"]
        c = a.get("content") or ""
        if is_discount(c):
            hits.append((a["id"], a.get("category_title"), a["title"], current_week(c), week_blocks(c)))

    print(f"Discount posts identified: {len(hits)} of {len(glob.glob(str(root / '*.json')))}\n")
    for i, cat, title, week, blocks in sorted(hits):
        print(f"id={i}  [{cat}]  {title}")
        print(f"    current week: {week}   (total {len(blocks)} weeks archived)")
        # Parse every historical block's range to a canonical id, checking coverage.
        ids = [week_id_from_range(rng) for rng, _ in blocks]
        bad = [rng for (rng, _), wid in zip(blocks, ids) if wid is None]
        print(f"    week-ids parsed: {len(ids) - len(bad)}/{len(ids)}"
              + (f"  UNPARSED: {bad}" if bad else "  (all ranges parsed)"))
        top = blocks[0][1] if blocks else {}
        for label, names in top.items():
            print(f"      {label}: {', '.join(names)}")
        print()
    return 0


if __name__ == "__main__":
    import sys
    if "--verify" in sys.argv:
        raise SystemExit(_verify())
    print(__doc__)
