# MandateGuard -- 90-120 second walkthrough video script

A shot-by-shot storyboard for a deterministic, rehearsable screen recording. Walks the dashboard **tab by tab, in the order a first-time viewer encounters it**: what the operator token is, then Fleet & controls, Live feed, Exposure, Held approvals, Agents, Policy replay, Receipts. Total target: **~115 seconds** (fits the 90-120s window). Record at 1280x900+ so dashboard text stays legible.

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
| 0:08-0:18 | Dashboard loads; point at the operator token field | Type/paste the operator token in, dashboard unlocks | "Every control action needs an authenticated operator token — this is what proves a human, not the agent, is the one pulling these levers." |
| 0:18-0:30 | Fleet & controls tab | Show current state: `Run state: RUNNING`, `Risk mode: NORMAL`, control epoch, policy version. Point at the Halt / Resume / Set-risk buttons | "This is fleet-wide command. Right now the fleet is running normally. From here an operator can halt every agent at once, or tighten the risk mode fleet-wide — both take a reason, and both are logged." |
| 0:30-0:42 | Fleet & controls: click Halt (type a reason first), then immediately trigger one request (simulator/terminal) showing instant `FLEET_HALTED` denial, then Resume | Run state flips to `HALTED`; next request denied; flips back to `RUNNING` | "Watch what halting does: the very next request — from any agent — is denied immediately. This is measured at under 100 milliseconds, not eventually consistent." |
| 0:42-0:52 | Fleet & controls: click Set risk ELEVATED, then back to NORMAL | Risk mode label changes; briefly show what tightens (lower approval threshold) | "Elevating risk mode fleet-wide tightens the approval threshold immediately — useful the moment something looks off, before you've even identified which agent." |
| 0:52-1:08 | Live feed tab | Submit a normal refund (simulator or `run_scenarios.py normal_refund`) — appears as ALLOW/SUCCEEDED. Submit a second one that gets denied (e.g. from the revoked demo agent) — appears as DENY with a reason code | "This is where every request lands as it happens. A legitimate refund is checked against policy and the agent's own judgment call is never trusted blindly — here it's authenticated, allowed, and executed. This one's denied outright, with the exact reason code attached — not a black box." |
| 1:08-1:18 | Exposure tab | Point at fleet/agent/customer budget bars filling toward their caps | "Every allowed refund reserves real budget here — per customer, per agent, and fleet-wide — so limits can't be quietly exceeded even under heavy load." |
| 1:18-1:32 | Held approvals tab | Trigger a high-value refund that lands HELD, type a reason, click Approve | "A high-value refund doesn't execute automatically — it's held for a human. Approving it re-checks live policy and current controls first, so it's never a rubber stamp." |
| 1:32-1:42 | Agents tab | Revoke an agent (reason required), show it, then Restore it | "An operator can revoke a single agent's authority instantly — anything that agent tries next is denied, without touching the rest of the fleet." |
| 1:42-1:52 | Policy replay tab | Paste a candidate config, click Run replay, show the diff table | "Before a policy change goes live, it can be replayed against real historical traffic to see exactly what would change — with zero risk to live state." |
| 1:52-2:00 | Receipts tab | Click Verify on a receipt, show the green VALID pill | "Every completed action has a cryptographically signed, independently verifiable receipt." |
| 2:00-2:05 | Closing card | Static: repo URL / project name / "Built and measured, not just claimed." | "MandateGuard: enforcement, not a policy document." |

Running total above is ~125s including the closing card -- see "Trimming to fit 90-120s" below for exactly what to cut to land inside the window.

## Trimming to fit 90-120s

The full walkthrough above runs a little over on a first pass. Cut in this order until you're inside the window:

1. **Drop the risk-mode beat (0:42-0:52)** first -- it's the same "operator lever, immediate effect" point the halt demo (0:30-0:42) already made.
2. **Drop the Agents-tab revoke (1:32-1:42)** next if still over -- it repeats the "one action, immediate denial" beat from both halt and the Live feed denial.
3. Everything else is load-bearing for the core thesis: token -> fleet control -> request judged and reasoned -> exposure reserved -> human approval re-checked -> receipt verified.

If you want the strongest possible proof-of-enforcement moment and have room to add one back in: a terminal shot of the direct-bank-bypass probe (`python scripts/run_scenarios.py direct_bypass`, showing `401 PERMIT_REQUIRED`) is the single most convincing 10 seconds in the whole demo -- it proves the agent *cannot* route around the broker, not just that it chooses not to. Slot it right after the Live feed section if you have 10 seconds to spare.

## Recording tips

- Reset dev state between takes (`scripts/reset_dev_state.sql`) so denials/holds/reason codes come out the same way every time.
- Keep a terminal window pre-positioned and minimized for any terminal-driven moment (halt-denial trigger, revoked-agent request, optional bypass probe) so there's no dead air switching windows.
- A silent captions-only cut (no voiceover) works too -- burn the "Voiceover" column text in as on-screen captions instead.
