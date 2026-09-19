# Home-server handoff — WRF discount pipeline

Finish wiring the WRFrontiers-News-Scraper pipeline on the **home server**. Runs
as the `dev` user on a systemd timer, 4×/day. Nothing runs on the workstation.

The systemd units themselves live in the **home-server** repo
(`home-server/systemd/hs-wrf-discount-watch.{service,timer}`) and are installed by
its `systemd/install.sh`. This repo just provides the scripts + archive.

## 0. Prerequisites (on the server, as `dev`)

- `python3` on PATH (stdlib only; no packages needed).
- `gh` authenticated as `dev` (it already is on this box):
  ```bash
  gh auth status
  gh auth status | grep -q "Logged in" || gh auth login   # only if needed
  ```
- Push/dispatch access to `Surxe/WRFrontiers-Discount-Visualizer` (the workflow is
  `workflow_dispatch`; dev must be able to trigger Actions there).

## 1. Clone this repo at the expected path

The units reference `/srv/dev/repos/WRFrontiers-News-Scraper` exactly.

```bash
cd /srv/dev/repos
git clone https://github.com/Surxe/WRFrontiers-News-Scraper.git
cd WRFrontiers-News-Scraper
```

## 2. Seed the archive + prime the state

Step 2 reads the archive step 1 produces, so build it once, then record the
**current** week as already-handled so the timer only fires on the *next* new
week (not re-dispatch what's already live):

```bash
python3 scripts/archive.py                 # full catalog (~5 min, polite 0.3s spacing)
python3 scripts/detect.py --verify         # sanity: should identify the discount post(s)
python3 scripts/watch_discount.py --prime  # record current week; dispatches nothing
```

`--prime` writes `data/watch_state.json` (gitignored). Verify it lists the current
week under `parsed_weeks`.

> Alternative: to push the **current** week to the visualizer once, right now,
> run `python3 scripts/watch_discount.py --dispatch` instead of `--prime`.

## 3. Dry-run the pipeline end to end

```bash
python3 scripts/archive.py --latest 3
python3 scripts/watch_discount.py --latest 3
```

With the state primed you should see `{"event":"no-change",...}`. To confirm the
dispatch wiring, temporarily clear the state and dry-run — you'll see the exact
`gh workflow run ...` command it *would* fire (no `--dispatch` = it only prints):

```bash
python3 scripts/watch_discount.py --latest 3   # look for "dispatch-dry-run" + the cmd
python3 scripts/watch_discount.py --prime      # re-prime afterwards
```

## 4. Install + enable the systemd units (as root)

From the home-server repo:

```bash
sudo /srv/dev/repos/home-server/systemd/install.sh
# or the whole host: sudo /srv/dev/repos/home-server/install.sh
```

This symlinks the units into `/etc/systemd/system`, reloads, and `enable --now`s
`hs-wrf-discount-watch.timer` (skipped automatically if this clone is missing).
Confirm:

```bash
systemctl list-timers hs-wrf-discount-watch.timer
```

## 5. Turn dispatch ON

The unit ships with `WRF_DISPATCH=0` (dry-run) so nothing fires until you're ready.
Enable real dispatch without editing the committed unit:

```bash
sudo systemctl edit hs-wrf-discount-watch.service
# in the drop-in editor add:
#   [Service]
#   Environment=WRF_DISPATCH=1
sudo systemctl daemon-reload
```

## 6. Test the live unit

```bash
sudo systemctl start hs-wrf-discount-watch.service
journalctl -u hs-wrf-discount-watch.service -n 30 --no-pager
```

Look for `discount-announced` then `dispatched` (or `no-change` if the current
week is already primed). Confirm the visualizer picked it up:

```bash
gh run list -R Surxe/WRFrontiers-Discount-Visualizer -L 3
```

## What happens each run

1. `archive.py --latest 3` — scrape + persist the 3 latest posts (idempotent).
2. `watch_discount.py --latest 3` — find the discount post, canonicalize its week,
   and if new: log `discount-announced` and dispatch `all.yml` with `items` +
   `target_date_range`. Deduped by canonical week id, so re-runs never re-fire.

## Tunables

- **Cadence** — `home-server/systemd/hs-wrf-discount-watch.timer` (`OnCalendar`,
  currently 04/10/16/22 America/Chicago).
- **How many latest posts to check** — `--latest N` on both scripts (default 3).
- **Map-only (no site deploy)** — add `--skip-deploy` to the watch step to pass
  `skip_deploy=true` to the visualizer.

## Still open (not part of this handoff)

- **Workstation rename fallout** — the workstation still has the old dir name
  `wrf-news-research` and my-system's snapshot launcher/desktop entry + repo list
  point at it. Separate my-system change; does not affect the server.
- **LLM name→id mapping** — a separate PR. The visualizer currently does its own
  fuzzy name mapping, so the pipeline hands it as-announced names for now.
