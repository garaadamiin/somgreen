# Restoring a SomGreen backup

An untested backup is not a backup. Work through the **drill** below once before
go-live, and once a quarter after. It takes about ten minutes and it is the only
thing that proves the backups are real.

A backup set is one folder under `D:\somgreen-backups\` containing:

| File | What it is |
|---|---|
| `somgreen.dump` | PostgreSQL custom-format dump |
| `filestore.zip` | Attachments, product images, generated PDFs |
| `docker-compose.yml`, `odoo.conf` | The stack as it was at backup time |
| `MANIFEST.txt` | When it was taken, from which host |

Both halves matter. Restoring the database without the filestore gives you a
system that looks complete until someone opens an invoice PDF or a product image
and gets a broken link.

---

## Drill: restore into a throwaway database

This does not touch production. Do this one first.

> **Never pipe the dump through PowerShell.**
> `Get-Content ... | docker exec -i pg_restore` and
> `docker exec ... pg_dump > file.dump` both corrupt the archive — PowerShell's
> pipeline and `>` redirect are text-mode and apply encoding conversion to
> binary. You get a plausible file of roughly the right size that pg_restore
> rejects. Always move dumps with `docker cp`, which is binary safe.

```powershell
$set = "D:\somgreen-backups\somgreen_20260815_020000"   # pick a real set
$tmp = "restore_test"

# 1. Copy the dump into the container (binary safe)
docker cp "$set\somgreen.dump" somgreen_db:/tmp/restore.dump

# 2. Confirm the archive is readable before trusting it
docker exec somgreen_db pg_restore --list /tmp/restore.dump | Select-Object -First 5

# 3. Create an empty target and restore into it
docker exec somgreen_db psql -U odoo -d postgres -c "CREATE DATABASE $tmp OWNER odoo;"
docker exec somgreen_db pg_restore -U odoo -d $tmp --no-owner /tmp/restore.dump

# 4. Sanity-check: are the books there?
docker exec somgreen_db psql -U odoo -d $tmp -tAc "SELECT count(*) FROM account_move WHERE state='posted';"
docker exec somgreen_db psql -U odoo -d $tmp -tAc "SELECT count(*) FROM stock_quant;"
docker exec somgreen_db psql -U odoo -d $tmp -tAc "SELECT count(*) FROM ir_module_module WHERE state='installed';"
```

Then neutralise the copy before opening it, so it cannot email customers or run
scheduled jobs against real data:

```powershell
docker exec somgreen_db psql -U odoo -d $tmp -c "UPDATE ir_cron SET active = false;"
docker exec somgreen_db psql -U odoo -d $tmp -c "DELETE FROM ir_mail_server;"
docker exec somgreen_db psql -U odoo -d $tmp -c "UPDATE ir_config_parameter SET value = 'restore-test' WHERE key = 'database.uuid';"
```

> **Why the uuid change matters.** Two databases sharing a `database.uuid` will
> both answer to the same Odoo enterprise/IAP identity. Always reset it on a copy.

Add `restore_test` to `dbfilter` in `config/odoo.conf` temporarily, restart the
app, log in, and click through: an invoice PDF, a product image, and a stock
valuation report. If those render, the backup is genuinely good. Once the
factory is live (Phase 2), open a manufacturing order too.

Clean up:

```powershell
docker exec somgreen_db psql -U odoo -d postgres -c "DROP DATABASE $tmp;"
```

---

## Real restore: production is gone

Only when you have accepted losing everything since the backup timestamp.

```powershell
$set = "D:\somgreen-backups\somgreen_20260815_020000"

# 1. Stop Odoo so nothing writes while you work
docker compose stop app

# 2. Move the damaged database aside rather than dropping it - it may still hold
#    recoverable data, and you get exactly one chance at this decision.
docker exec somgreen_db psql -U odoo -d postgres -c "ALTER DATABASE somgreen RENAME TO somgreen_damaged_$(Get-Date -f yyyyMMdd);"

# 3. Recreate and restore (docker cp, never a PowerShell pipe - see above)
docker exec somgreen_db psql -U odoo -d postgres -c "CREATE DATABASE somgreen OWNER odoo;"
docker cp "$set\somgreen.dump" somgreen_db:/tmp/restore.dump
docker exec somgreen_db pg_restore --list /tmp/restore.dump | Select-Object -First 3
docker exec somgreen_db pg_restore -U odoo -d somgreen --no-owner /tmp/restore.dump

# 4. Restore the filestore - this half is the one people forget
Remove-Item "D:\somgreen\odoo-web-data\filestore\somgreen" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "D:\somgreen\odoo-web-data\filestore\somgreen" -Force | Out-Null
Expand-Archive "$set\filestore.zip" -DestinationPath "D:\somgreen\odoo-web-data\filestore\somgreen" -Force

# 5. Back up
docker compose start app
docker compose logs -f app
```

Then, before telling anyone the system is back: log in, open the Balance Sheet,
and confirm the closing figures match the last known-good report. A restore that
completes without error can still land you on an older set than you meant.

---

## What is not covered

`.env` and `config/odoo.conf` are gitignored, so they are **not** in the git
repository. The backup set includes a copy of `odoo.conf`, but not `.env`. Keep
the passwords in a password manager as well — restoring the data does you no good
if nothing can authenticate to it.
