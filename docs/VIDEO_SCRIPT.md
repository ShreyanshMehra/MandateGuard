# MandateGuard -- 90-120 second walkthrough video script

A shot-by-shot storyboard for a deterministic, rehearsable screen recording. Total target: **105 seconds** (fits the 90-120s window with margin for pacing). Record at 1280x900+ so dashboard text stays legible.

## Before recording

```powershell
docker compose up -d
docker cp scripts/reset_dev_state.sql mandateguard-postgres-1:/tmp/reset_dev_state.sql
docker compose exec -T postgres psql -U mandateguard_admin -d mandateguard -f /tmp/reset_dev_state.sql
```

Open `http://localhost:5173/`, enter the operator token, and confirm all seven tabs load before you hit record. Do one silent dry run first -- this script assumes the same dev-state baseline `scripts/run_scenarios.py` uses, so a rehearsed take should be frame-for-frame reproducible.

## Shot list

| Time | Shot | On-screen action | Voiceover (or on-screen caption) |
|---|---|---|---|
| 0:00-0:08 | Title card | Static: "MandateGuard — a governance layer for financial AI agents" over the architecture diagram (or the deck's title slide) | "MandateGuard makes sure no AI agent can move money without bounded authority, reserved exposure, and proof." |
| 0:08-0:20 | Dashboard: Fleet & controls tab | Show governance status (RUNNING/NORMAL), fleet exposure bar | "This is the live operator dashboard. Right now the fleet is running normally, with real budget exposure tracked per customer, agent, and fleet." |
| 0:20-0:35 | Dashboard: Live feed tab, then submit one refund (via `run_scenarios.py` scenario 1 or the agent simulator) | A normal refund appears in the feed as SUCCEEDED with a receipt | "A legitimate refund request is authenticated, checked against policy, and executed — with a signed receipt, every time." |
| 0:35-0:50 | Dashboard: Held approvals tab | Trigger a high-value refund (scenario 2), show it land as HELD, click Approve | "A high-value refund is held for a human. Approving it re-checks live policy and current controls before it can execute — never a rubber stamp." |
| 0:50-1:02 | Terminal: direct-bank bypass probe (scenario 4) | Run the probe, show `401 PERMIT_REQUIRED` | "An agent — or an attacker — cannot call the bank directly. Only the broker holds the service credential and a valid signed permit." |
| 1:02-1:14 | Dashboard: Fleet & controls tab | Click Halt, then show a new request immediately denied (`FLEET_HALTED`) | "One operator action halts the entire fleet. The very next request is denied — measured in milliseconds, not minutes." |
| 1:14-1:26 | Dashboard: Exposure tab, then a concurrent burst (scenario 5, via `run_scenarios.py`) | Show the burst result: exactly N succeeded against a shared cap, never more | "Under real concurrent load, budget limits hold exactly — zero overshoot, proven, not assumed." |
| 1:26-1:38 | Dashboard: Policy replay tab | Load a candidate config, run replay, show the diff table | "Before a policy change goes live, we can replay it against real historical traffic and see exactly what would change — with zero risk to live state." |
| 1:38-1:45 | Dashboard: Receipts tab | Click Verify on a receipt, show the green VALID pill | "Every completed action has a cryptographically verifiable receipt." |
| 1:45-1:50 | Closing card | Static: repo URL / project name / "Built and measured, not just claimed." | "MandateGuard: enforcement, not a policy document." |

## Recording tips

- Resume/un-halt the fleet between takes (`scripts/reset_dev_state.sql` does this automatically).
- If timing runs long, cut the policy-replay shot (1:26-1:38) first -- it's the most skippable without losing the core thesis (identity -> policy -> budget -> permit -> execution -> receipt -> halt).
- Keep a terminal window pre-positioned for the bypass-probe shot (0:50-1:02) so there's no dead air switching windows; consider running `python scripts/run_scenarios.py direct_bypass` just before recording so the output is fresh in scrollback.
- A silent captions-only cut (no voiceover) works too -- burn the "Voiceover" column text in as on-screen captions instead.
