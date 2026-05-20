# Backup & Restore Guide

## Overview
This guide explains how to backup, restore, and schedule automatic backups for the MedQueue PostgreSQL database.

## Files
- `startup/backend/scripts/backup.sh` — Backup script (exports DB to SQL file)
- `startup/backend/scripts/restore.sh` — Restore script (imports SQL file back to DB)

## Manual Backup

### On Local Machine (docker-compose running)
```bash
mkdir -p ./backups
./startup/backend/scripts/backup.sh ./backups
# Result: ./backups/medqueue_db_backup_YYYYMMDD_HHMMSS.sql
```

### On Remote Server (production)
```bash
mkdir -p /opt/medqueue/backups
cd /opt/medqueue
./startup/backend/scripts/backup.sh /opt/medqueue/backups
# Result: /opt/medqueue/backups/medqueue_db_backup_YYYYMMDD_HHMMSS.sql
```

## Manual Restore

### Test Restore Locally
```bash
# 1. Start docker-compose normally
docker compose -f startup/docker-compose.yml up -d

# 2. Backup current DB
./startup/backend/scripts/backup.sh ./backups

# 3. Restore from a backup file
./startup/backend/scripts/restore.sh ./backups/medqueue_db_backup_YYYYMMDD_HHMMSS.sql

# 4. Verify restoration
docker exec medqueue-db psql -U medqueue medqueue -c "SELECT COUNT(*) FROM appointments_doctor;"
```

### Restore on Production
```bash
cd /opt/medqueue
# Before restoring, optionally backup current state
./startup/backend/scripts/backup.sh /opt/medqueue/backups

# Restore from a specific backup
./startup/backend/scripts/restore.sh /opt/medqueue/backups/medqueue_db_backup_YYYYMMDD_HHMMSS.sql

# Verify
docker exec medqueue-db psql -U medqueue medqueue -c "SELECT COUNT(*) FROM appointments_doctor;"
```

## Automatic Backups via Cron

### Set Up Cron on Server

Edit crontab:
```bash
sudo crontab -e
# or as regular user
crontab -e
```

Add line for daily backup at 3 AM:
```cron
0 3 * * * cd /opt/medqueue && ./startup/backend/scripts/backup.sh /opt/medqueue/backups >> /var/log/medqueue/backup.log 2>&1
```

Or use `root` cron if `medqueue` user doesn't have docker permissions:
```bash
sudo crontab -e
# Add:
0 3 * * * docker exec medqueue-db pg_dump -U medqueue medqueue > /opt/medqueue/backups/medqueue_db_backup_$(date +\%Y\%m\%d_\%H\%M\%S).sql >> /var/log/medqueue/backup.log 2>&1
```

### Verify Cron Setup
```bash
crontab -l  # View scheduled tasks
tail -f /var/log/medqueue/backup.log  # Monitor backup logs
ls -lh /opt/medqueue/backups  # Check backup files
```

## Alternative: systemd Timer

If you prefer systemd over cron:

Create `/etc/systemd/system/medqueue-backup.service`:
```ini
[Unit]
Description=MedQueue Database Backup
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/medqueue
ExecStart=/opt/medqueue/startup/backend/scripts/backup.sh /opt/medqueue/backups
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/medqueue-backup.timer`:
```ini
[Unit]
Description=MedQueue Database Backup Timer
Requires=medqueue-backup.service

[Timer]
OnCalendar=03:00  # Run daily at 3 AM
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable medqueue-backup.timer
sudo systemctl start medqueue-backup.timer
sudo systemctl status medqueue-backup.timer
```

## Backup Retention Policy

To keep only the last 7 days of backups, add to crontab:
```cron
0 4 * * * find /opt/medqueue/backups -name "medqueue_db_backup_*.sql" -mtime +7 -delete
```

## Testing Restore (Recommended)

Run this test weekly or after major changes:

```bash
#!/bin/bash
# test_restore.sh - Test that backups can be restored
BACKUP_DIR="/opt/medqueue/backups"
LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/medqueue_db_backup_*.sql 2>/dev/null | head -1)

if [ -z "$LATEST_BACKUP" ]; then
  echo "No backup found!"
  exit 1
fi

echo "Testing restore from: $LATEST_BACKUP"

# Create a test container (optional: spin up a test DB)
# For now, just validate SQL syntax
if sql file=$(sqlite3 /tmp/test.db < "$LATEST_BACKUP" 2>&1); then
  echo "Backup file appears valid"
else
  echo "Backup file may be corrupted!"
  exit 1
fi

echo "Restore test completed"
```

## Monitoring & Alerts

Consider setting up monitoring for backup success. Example:
```bash
# Check backup age (alert if > 24 hours old)
LATEST=$(ls -t /opt/medqueue/backups/medqueue_db_backup_*.sql 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
  echo "ALERT: No backup found!" | mail -s "MedQueue Backup Alert" admin@example.com
fi
AGE=$(($(date +%s) - $(stat -f%m "$LATEST" 2>/dev/null || stat -c%Y "$LATEST")))
if [ "$AGE" -gt 86400 ]; then
  echo "ALERT: Backup is older than 24 hours" | mail -s "MedQueue Backup Alert" admin@example.com
fi
```

## Disaster Recovery Plan

1. **Automated backups run daily at 3 AM** → `/opt/medqueue/backups/`
2. **Retention**: Keep 7 days of backups (oldest deleted automatically)
3. **Testing**: Run manual restore test monthly
4. **Storage**: Store backup copies off-site (e.g., S3, cloud storage)
5. **RTO/RPO**: Recovery Time Objective ≈ 30 minutes (manual restore), Recovery Point Objective = last backup (daily)

## Quick Reference

```bash
# Backup now
/opt/medqueue/startup/backend/scripts/backup.sh /opt/medqueue/backups

# Restore from a backup
/opt/medqueue/startup/backend/scripts/restore.sh /opt/medqueue/backups/medqueue_db_backup_YYYYMMDD_HHMMSS.sql

# Check backups
ls -lh /opt/medqueue/backups

# View cron jobs
crontab -l

# Check backup logs
tail -f /var/log/medqueue/backup.log

# Test if DB is accessible
docker exec medqueue-db psql -U medqueue medqueue -c "SELECT now();"
```
