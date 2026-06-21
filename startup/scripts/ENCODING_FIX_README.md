Encoding-fix workflow (CP866 -> UTF-8)
====================================

Purpose
- Provide a safe, repeatable process to inspect a PostgreSQL SQL dump for encoding problems and produce a CP866->UTF-8 converted SQL file for testing.

Files
- `encoding_fix_workflow.sh` — script to create a working copy of the dump, detect UTF-8 validity, convert from CP866 to UTF-8 using `iconv`, and print before/after samples.

Prerequisites
- A Unix-like environment (server, WSL, or container) with `gunzip`, `iconv`, and optionally `docker` for testing restores.

Quick run
1. Copy the downloaded dump to the machine where you'll run checks, e.g. `/tmp/medqueue_db_backup_2026-05-22.sql.gz`
2. Run the script:
   ```bash
   chmod +x encoding_fix_workflow.sh
   ./encoding_fix_workflow.sh /tmp/medqueue_db_backup_2026-05-22.sql.gz /tmp/encoding_check
   ```
3. The script will create `/tmp/encoding_check/medqueue_db_backup_2026-05-22.sql` and, if needed, `/tmp/encoding_check/medqueue_db_backup_2026-05-22.converted.utf8.sql` and will display sample lines before/after.

Testing the converted dump
- Use a disposable Postgres instance to test restore and inspect data. Example:
  ```bash
  docker run --rm --name tmp-pg -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=testdb -d postgres:15-alpine
  docker exec -i tmp-pg psql -U postgres -d testdb < /path/to/medqueue_db_backup_2026-05-22.converted.utf8.sql
  docker exec -it tmp-pg psql -U postgres -d testdb
  # run select queries to validate text columns
  ```

If conversion is correct
- After manual validation in a staging/test DB, you can plan a production rollout:
  - Take a fresh production dump and store off-server
  - Restore the converted dump to a staging DB and run application-level tests
  - Schedule a maintenance window and restore the validated dump to production (only after full backup and rollback plan)

Safety notes
- Always keep the original dump untouched. Work only on copies.
- Verify converted data carefully before any destructive action on production.
