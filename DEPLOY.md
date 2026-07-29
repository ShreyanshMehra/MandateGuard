# Deploying MandateGuard for free (Render)

A step-by-step guide to putting the real, working stack (dashboard + broker
+ mock bank + OPA + Postgres) behind a public URL at no cost, using
[Render](https://render.com)'s free web-service tier. Read the disclosed
tradeoff at the top of `render.yaml` first -- the short version: on Render's
free plan, every service ends up with a public URL (private services
require a paid plan), so the mock bank is reachable from the internet in
this deployment, unlike the local `docker-compose` stack. It still refuses
every request without the broker's shared secret and a valid signed permit
-- that protection is in application code, not network placement -- but the
network-level isolation claim in `docs/ARCHITECTURE.md` only fully holds
locally. Say so if anyone asks how this deployment differs from the design.

This whole thing takes about 20-30 minutes, is entirely free, and doesn't
require a credit card for the services themselves (Render's Postgres free
instance may ask you to verify an account, but does not charge).

## 0. Before you start

- Push everything to GitHub first (Render deploys from a connected repo,
  not from your local machine): `render.yaml` and `docker/deploy/` need to
  be committed and pushed to `origin/main`.
- Have `RENDER_SECRETS_LOCAL_ONLY.md` open (it's git-ignored, local only) --
  you'll copy three private keys and two token values out of it.
- Create a free account at render.com if you don't have one (GitHub sign-in
  is easiest).

## 1. Create the Blueprint

1. In the Render dashboard: **New +** -> **Blueprint**.
2. Connect your GitHub account if prompted, then select the `MandateGuard`
   repository.
3. Render finds `render.yaml` at the repo root and shows you the four
   services (`mandateguard-opa`, `mandateguard-mock-bank`,
   `mandateguard-broker`, `mandateguard-frontend`) plus the
   `mandateguard-db` Postgres instance it's about to create.
4. When prompted for the `sync: false` environment variables
   (`BROKER_SERVICE_TOKEN`, `OPERATOR_TOKEN`, `DATABASE_URL`,
   `ADMIN_DATABASE_URL`), you can leave `DATABASE_URL`/`ADMIN_DATABASE_URL`
   blank for now -- you'll fill them in after step 3 below. Set
   `BROKER_SERVICE_TOKEN` and `OPERATOR_TOKEN` now using the generated
   values from `RENDER_SECRETS_LOCAL_ONLY.md` (or generate your own with
   `python -c "import secrets; print(secrets.token_urlsafe(24))"`).
5. Click **Apply**. Render starts building all four services. The first
   build will fail for `mandateguard-broker` and `mandateguard-mock-bank`
   (no database connection yet) -- that's expected, continue to step 2.

## 2. Set up the database roles and schemas (one-time, manual)

Render's managed Postgres gives you one admin role and doesn't run the
custom init script `database/init/00-roles-and-schemas.sh` uses locally, so
run it once by hand.

1. In the Render dashboard, open **mandateguard-db** -> note its **External
   Database URL** (starts with `postgresql://`).
2. From your own machine (psql needs to reach it over the public internet
   for this one-time step -- Render Postgres allows external connections by
   default):
   ```powershell
   psql "<external-database-url-from-render>"
   ```
3. Pick two passwords for the two scoped roles (anything reasonably
   random), then run, substituting them in:
   ```sql
   CREATE ROLE mandateguard_broker LOGIN PASSWORD '<pick-a-password-1>';
   CREATE ROLE mandateguard_bank LOGIN PASSWORD '<pick-a-password-2>';

   CREATE SCHEMA IF NOT EXISTS broker AUTHORIZATION mandateguard_broker;
   CREATE SCHEMA IF NOT EXISTS bank AUTHORIZATION mandateguard_bank;

   REVOKE ALL ON SCHEMA bank FROM mandateguard_broker;
   REVOKE ALL ON SCHEMA broker FROM mandateguard_bank;
   REVOKE ALL ON SCHEMA bank FROM PUBLIC;
   REVOKE ALL ON SCHEMA broker FROM PUBLIC;

   ALTER ROLE mandateguard_broker SET search_path = broker;
   ALTER ROLE mandateguard_bank SET search_path = bank;
   ```
   This is the exact same SQL `database/init/00-roles-and-schemas.sh` runs
   automatically for the local Compose stack -- here it's just a one-time
   manual step instead.
4. `\q` to exit psql.

## 3. Set the database connection env vars

Still in the Render dashboard, open **mandateguard-db** and copy its
**Internal Database URL** (starts with `postgresql://`, host looks like
`mandateguard-db:5432` or similar -- internal is faster and doesn't count
against any external-connection limits). You'll build three variants of it,
swapping in the roles from step 2:

- **`mandateguard-broker`** service -> Environment -> add/edit:
  - `ADMIN_DATABASE_URL` = the internal URL as-is, but with the scheme
    changed from `postgresql://` to `postgresql+psycopg://` (SQLAlchemy
    needs the driver name in the scheme) -- this uses Render's own admin
    role, needed once per boot to run `alembic upgrade head`.
  - `DATABASE_URL` = same host/port/db, but
    `postgresql+psycopg://mandateguard_broker:<password-1-from-step-2>@<host>:5432/<db-name>`
- **`mandateguard-mock-bank`** service -> Environment -> add/edit:
  - `DATABASE_URL` = `postgresql+psycopg://mandateguard_bank:<password-2-from-step-2>@<host>:5432/<db-name>`

## 4. Upload the three secret files

Per `RENDER_SECRETS_LOCAL_ONLY.md`:

- **`mandateguard-broker`** -> Environment -> Secret Files -> add
  `broker-permit-signing.pem` and `audit-checkpoint-signing.pem` (paste the
  contents from the local file).
- **`mandateguard-mock-bank`** -> Environment -> Secret Files -> add
  `bank-result-signing.pem`.

## 5. Redeploy

Each service you edited needs a manual redeploy to pick up the new env
vars/secret files: open each of `mandateguard-broker` and
`mandateguard-mock-bank` -> **Manual Deploy** -> **Deploy latest commit**.
Watch the logs -- `mandateguard-broker`'s log should show Alembic applying
migrations, then Uvicorn starting.

## 6. Use it

Once all four services show **Live**:

- Dashboard: `https://mandateguard-frontend.onrender.com`
- Enter the `OPERATOR_TOKEN` value you set in step 1.
- Broker API directly: `https://mandateguard-broker.onrender.com` (e.g.
  `/health`, `/ready`).

To run the deterministic demo scenarios against the deployed stack from
your own machine:

```powershell
$env:BROKER_URL = "https://mandateguard-broker.onrender.com"
$env:OPERATOR_TOKEN = "<your OPERATOR_TOKEN value>"
python scripts/run_scenarios.py
```

## Known free-tier limitations

- **Cold starts.** Free web services spin down after 15 minutes of no
  traffic and take 30-60 seconds to wake back up on the next request --
  the first click after idle time will feel slow. Fine for a submission
  link people click occasionally; not fine for a live judged demo without
  a warm-up request first.
- **Postgres expires after 90 days** on Render's free plan (Render emails a
  warning first). If it expires, recreate it and repeat steps 2-5.
- **No true network isolation** for the mock bank, as noted at the top --
  see `render.yaml`'s header comment for the full explanation.
- **Shared free-tier resource caps** (RAM/CPU) are much lower than your
  local machine -- the concurrent-burst scenario may behave differently
  under real network latency than it does locally; that's expected and not
  a regression in the underlying guarantee (budget reservation is still
  atomic at the database level regardless of request latency).
