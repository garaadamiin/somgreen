# Rebuild procedures — technical

Platform-level procedures for SomGreen ERP. Everything here is command line and
is **not** required for the configuration work in `SETUP.md`.

Use this file when rebuilding the instance from nothing, or when investigating a
platform fault. Day-to-day configuration is done in the Odoo interface and is
documented in `SETUP.md`.

---

## 1. Start the stack

Start Docker Desktop, then:

```bash
docker compose up -d
```

### Filestore ownership — required after any rebuild

If `postgres-data/` or `odoo-web-data/` were deleted, fix ownership before doing
anything else:

```bash
docker compose exec -u root app chown -R 100:101 /var/lib/odoo
docker compose restart app
```

Docker recreates a deleted bind-mount directory as `root:root`, but Odoo runs as
uid `100`. Without this it cannot create `/var/lib/odoo/sessions` and **every**
request returns HTTP 500 — including the `/web/health` check, which is also why
the container reports `unhealthy`. The database is irrelevant to this failure; it
occurs before Odoo reads from it.

Postgres needs no equivalent step: its entrypoint chowns `pgdata` itself, which
is why the database container comes up clean while Odoo does not.

Both services must report `healthy`:

```bash
docker compose ps
```

---

## 2. Create the database and install modules

The web database manager cannot be used. `list_db = False` in `config/odoo.conf`
causes `database_manager.qweb.html` to wrap its entire body in `t-if="list_db"`,
so `/web/database/manager` returns HTTP 200 but renders only *"The database
manager has been disabled by the administrator"*. There is no create form.

Create from the command line, which also installs the modules:

```bash
docker compose run --rm app odoo -d somgreen -i om_account_accountant,stock,purchase,sale_management,somgreen_config,somgreen_account_reports --without-demo=all --workers=0 --max-cron-threads=0 --stop-after-init
```

- `-d` on a database that does not exist creates it.
- `--without-demo=all` is the equivalent of unchecking Demo data. This matters;
  demo data is very difficult to remove afterwards.
- `--workers=0` is required because `odoo.conf` sets `workers = 2`, which
  misbehaves under `--stop-after-init`.

`om_account_accountant` is an umbrella module and pulls in the other seven
accounting modules. `somgreen_config` pulls in `stock_account` and
`stock_landed_costs`. `somgreen_account_reports` carries the Balance Sheet and
Profit and Loss, and depends on `accounting_pdf_reports` — which the umbrella has
already brought in by the time it loads.

**Do not install `somgreen_mrp`.** That is the factory, and it is Phase 2.

---

## 3. Build the chart of accounts

```bash
docker compose run --rm -T -v "D:/somgreen/data/phase1-trading:/mnt/data" app odoo shell -d somgreen --workers=0 --max-cron-threads=0 --log-level=warn < scripts/setup_chart_of_accounts.py
```

```bash
docker compose restart app
```

Expect **80 accounts** and `missing from our chart: none`.

### Why this is a script and not a UI import

`data/phase1-trading/accounts.csv` cannot simply be imported. Odoo's generic
chart is already loaded by this point, and the two charts overlap three ways:

1. Two codes collide outright (101300, 201100) and the import aborts with
   *"Account codes must be unique"*.
2. Twelve further accounts mean the same thing under a different code or
   spelling. These import **silently**, leaving two accounts per concept — a
   worse outcome than an error, because nothing reports it.
3. The generic accounts are wired into journals and into `ir.default`, so
   deleting them first is not possible either.

The script retargets instead: where the generic chart already carries a concept
we also carry, it rewrites that account's code and name to ours and keeps the
record id. Every journal default, partner default and category default that
pointed at it stays valid without repointing. Only genuinely new accounts are
created. The script is idempotent.

It also repoints the five `product.category` defaults and the two journal
defaults onto our accounts, which is what allows Section 3 of `SETUP.md` to be
mostly confirmation rather than data entry.

`scripts/setup_chart_of_accounts.py` records which generic accounts are retained
deliberately — bank suspense, the outstanding payment pair, liquidity transfer,
undistributed profit and loss, and the two tax accounts referenced by tax
repartition lines. Removing any of these breaks payment registration, bank
reconciliation, tax or year-end close.

---

## 4. Register the scheduled backup

Not currently registered. Every backup so far has been run manually.

```powershell
schtasks /Create /TN "SomGreen Backup" /RL HIGHEST /SC DAILY /ST 02:00 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File d:\somgreen\scripts\backup.ps1"
```

```powershell
schtasks /Query /TN "SomGreen Backup"
```

Restore procedure is in `scripts/RESTORE.md`. Run the restore drill once before
real data exists.

---

## 5. Logs and diagnostics

The application log is `logs/odoo.log`, bind-mounted so it survives container
recreation.

```bash
docker compose logs app
```

shows container-level output only. **The detail is in the file, not in
`docker compose logs`.** The previous build's log is retained as
`logs/odoo.log.pre-rebuild`.

---

## 6. Known platform faults

| Symptom | Cause |
|---|---|
| Every page returns HTTP 500, container `unhealthy` | Filestore ownership. Section 1. |
| *"The database manager has been disabled by the administrator"* | Expected behaviour of `list_db = False`. Create databases from the command line. Section 2. |
| Odoo cannot connect to Postgres | `db_password` in `config/odoo.conf` overrides the `.env` value. If rotated, all three must change together — see `README.md`. |
| Websocket requests return 500 | `workers = 2` runs the websocket on the gevent port, but nothing routes `/websocket` to it without a reverse proxy. Degrades live notifications only; does not affect transactions. |
| Import rejected with *"Account codes must be unique"* | The generic chart already holds that code. Do not renumber by hand — run `setup_chart_of_accounts.py`, Section 3. |
