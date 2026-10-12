# Backup and restore

```bash
./manage.sh backup              # backups/lalitstock_YYYYMMDD_HHMMSS.sql.gz (pg_dump --clean, gzip-verified)
./manage.sh restore             # pick from a list; type RESTORE to confirm
./manage.sh restore backups/lalitstock_20261012_123207.sql.gz
```

- A restore first takes a **safety backup** of the current state, stops the backend, loads the dump, restarts, and runs migrations (so an older backup is upgraded to the current schema).
- Backups contain the database only. Back up `.env` separately and securely: `APP_SECRET_KEY` is needed to decrypt stored AI keys and to validate existing device API keys.
- Copy `backups/` off the server regularly. Example nightly cron on the VPS: `0 2 * * * cd /opt/lalitstock && ./manage.sh backup -y`.
- Test restores periodically on a staging copy.
- `./manage.sh reset` → option 1 removes demo data only. Option 2 resets all application data (keeping users and settings) after a confirmation word and an automatic backup.
