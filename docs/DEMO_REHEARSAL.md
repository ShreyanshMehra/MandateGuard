# MandateGuard -- live demo rehearsal checklist

For rehearsing the live judged demo (as opposed to the recorded video -- see `docs/VIDEO_SCRIPT.md`). Goal: the judge can watch the full story from the dashboard alone, with the terminal only as backup evidence.

## T-minus setup (do this before the judge sits down)

- [ ] `docker compose up -d`; confirm all six containers are `healthy`/`Up` (`docker compose ps`).
- [ ] Reset dev state so the run is deterministic:
  ```powershell
  docker cp scripts/reset_dev_state.sql mandateguard-postgres-1:/tmp/reset_dev_state.sql
  docker compose exec -T postgres psql -U mandateguard_admin -d mandateguard -f /tmp/reset_dev_state.sql
  ```
- [ ] Open `http://localhost:5173/` in a full-screen browser window; enter the operator token; confirm all seven tabs load with data.
- [ ] Have a terminal ready (but minimized) for the two moments that need it: the direct-bank-bypass probe and, as a fallback, `python scripts/run_scenarios.py`.
- [ ] Do one full silent dry run of the sequence below within the last hour before presenting -- confirms live budget headroom hasn't been eaten by earlier rehearsals.
- [ ] If a live run is interrupted or the dashboard ends up in a confusing state (mid-halt, an agent left revoked, etc.), the fastest recovery is another dev-state reset, not manual cleanup clicks.

## Live sequence (dashboard-first, ~4-6 minutes with narration)

1. **Fleet & controls** -- show `RUNNING` / `NORMAL`, point out the exposure numbers are real, not mocked.
2. **Live feed** -- submit a normal refund (agent simulator or `scripts/run_scenarios.py normal_refund`); point out it lands as `SUCCEEDED` within the feed automatically (polling, no manual refresh).
3. **Held approvals** -- trigger a high-value refund; it lands `HELD`; approve it from the dashboard; narrate that approval re-checks live policy, not just a stored decision.
4. **Terminal (30 seconds)** -- run the direct-bank-bypass probe; show the `401 PERMIT_REQUIRED` response; this is the one moment worth leaving the browser for, because it's the clearest "the agent literally cannot do this" proof.
5. **Fleet & controls** -- click Halt; immediately submit a request from the terminal or simulator; show the instant `FLEET_HALTED` denial; resume.
6. **Exposure + a concurrent burst** -- run the concurrent-burst scenario; show the exposure numbers land exactly at the cap, never over.
7. **Policy replay** -- paste a candidate config, run replay, walk through the diff table; emphasize live state is untouched (flip back to Live feed to show the original action's status didn't change).
8. **Receipts** -- click Verify on any receipt; show the green `VALID` pill; mention the signature is checked live, not just displayed from storage.
9. **Agents** (only if time remains) -- revoke an agent, show a new request from it immediately denied `AGENT_INACTIVE`, restore it.

## Fallback plan

If live narration runs short on time or something in the environment misbehaves, `python scripts/run_scenarios.py` runs all eleven scenarios unattended and prints PASS/FAIL plus the key metric for each -- have it ready as a terminal-only backup that still proves every claim, just without the dashboard visuals.

## Backup recording

Keep the recorded video (`docs/VIDEO_SCRIPT.md`) ready to play as a fallback in case of live environment failure (network issue, Docker Desktop hiccup, projector/demo-machine problem). Test the backup recording plays correctly on the actual presentation machine/software before the judged session, not just on the machine it was recorded on.

## Known rough edges to narrate around, not hide

- One test in the automated suite is skipped when the shared fleet budget doesn't have headroom left in the same pytest run for a HOLD-triggering amount -- this is a test-isolation artifact of a shared dev database, not a product bug; a reset before the run avoids it entirely (see `STATUS.md`'s verification log).
- The dashboard has no dedicated operator login yet -- it uses the same shared dev token as the API. If asked, this is a documented, deliberate scope reduction (see `HANDOFF.md` Milestone 6 notes), not an oversight.
