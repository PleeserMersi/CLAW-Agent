# outside_cron.sh - Automated Scheduling Guide

Manage daily automated runs of the CLAW-Agent pipeline using cron.

---

## Overview

`outside_cron.sh` creates, updates, or removes a daily cron job that automatically runs the CLAW-Agent fault extraction pipeline at a specified time. This is useful for:

- **Regular data collection**: Run the pipeline daily without manual intervention
- **Off-peak processing**: Schedule runs during low-usage hours (e.g., 2:00 AM)
- **Consistent reporting**: Generate daily fault reports on a fixed schedule

---

## Location

```bash
/home/sec-researchonly/Desktop/CLAW-Agent/scripts/outside_cron.sh
```

---

## Usage

### Set Daily Schedule

```bash
./scripts/outside_cron.sh HH:MM
```

**Arguments:**
- `HH:MM` - Time to run daily (24-hour format)

**Examples:**

```bash
# Run daily at 2:00 AM
./scripts/outside_cron.sh 02:00

# Run daily at 6:30 PM
./scripts/outside_cron.sh 18:30

# Run daily at midnight
./scripts/outside_cron.sh 00:00
```

### Check Current Status

```bash
./scripts/outside_cron.sh
```

Shows whether a cron job is active and displays the current schedule.

### Remove Cron Job

```bash
./scripts/outside_cron.sh --remove
# or
./scripts/outside_cron.sh -r
```

---

## How It Works

### Cron Entry Created

When you set a schedule (e.g., `02:00`), the script creates this cron entry:

```cron
0 2 * * * cd /home/sec-researchonly/Desktop/CLAW-Agent && ./scripts/run_pipeline.sh >> /home/sec-researchonly/Desktop/CLAW-Agent/cron_pipeline.log 2>&1
```

**Breakdown:**
- `0 2 * * *` - Run at 2:00 AM every day
- `cd /home/sec-researchonly/Desktop/CLAW-Agent` - Change to project root
- `./scripts/run_pipeline.sh` - Execute the pipeline
- `>> cron_pipeline.log 2>&1` - Append all output (stdout + stderr) to log file

### Log File

All cron job output is written to:

```bash
/home/sec-researchonly/Desktop/CLAW-Agent/cron_pipeline.log
```

**View recent logs:**
```bash
tail -f cron_pipeline.log
```

**Check last run output:**
```bash
tail -100 cron_pipeline.log
```

---

## Default Pipeline Behavior

When run via cron, the pipeline uses these defaults:

- **Date Range**: 2 days ago to 1 day ago
- **Halls**: All halls (hall_a, hall_b, hall_c, hall_d)
- **Batch Sizes**: extract=5, tag=10, filter=10, validation=10, fixing=10
- **Filtering**: Disabled

### Customizing Cron Pipeline

If you need different parameters for automated runs, you have two options:

**Option 1: Modify the script directly**

Edit `scripts/outside_cron.sh` and change the cron entry to include your preferred flags:

```bash
# In the create_cron_job function, modify this line:
local cron_entry="$minute $hour * * * cd $PROJECT_ROOT && $PIPELINE_SCRIPT --filter --extract-size 10 --tag-size 20 >> $PROJECT_ROOT/cron_pipeline.log 2>&1"
```

**Option 2: Create a wrapper script**

```bash
# Create scripts/cron_pipeline_wrapper.sh
#!/bin/bash
cd /home/sec-researchonly/Desktop/CLAW-Agent
./scripts/run_pipeline.sh --filter --extract-size 10 --tag-size 20
```

Then point the cron job to the wrapper instead of `run_pipeline.sh`.

---

## Troubleshooting

### "Cron job not running"

**Check if cron service is running:**
```bash
systemctl status cron
# or
service cron status
```

**Start cron if needed:**
```bash
sudo systemctl start cron
sudo systemctl enable cron  # Auto-start on boot
```

**Verify the cron entry exists:**
```bash
crontab -l | grep run_pipeline
```

### "No output in log file"

The pipeline may have failed silently. Check:

1. **Environment variables**: Cron jobs don't inherit your shell's `.env`
   - Solution: Source `.env` in the cron entry or set variables directly
   
2. **Permissions**: Ensure the script is executable
   ```bash
   chmod +x scripts/run_pipeline.sh
   chmod +x scripts/outside_cron.sh
   ```

3. **Python/virtualenv**: Cron may not find your Python
   - The `run_pipeline.sh` script auto-activates the venv, so this should work

### "Wrong time zone"

Cron uses the system's local time zone. To verify:

```bash
# Check system time zone
timedatectl

# View cron daemon logs
grep CRON /var/log/syslog | tail -20
```

If you need a different time zone, set it in the cron entry:

```cron
# Run at 2:00 AM America/New_York
CRON_TZ=America/New_York
0 2 * * * cd /home/sec-researchonly/Desktop/CLAW-Agent && ./scripts/run_pipeline.sh >> cron_pipeline.log 2>&1
```

### "Multiple cron jobs created"

The script removes existing CLAW-Agent jobs before creating new ones. If you see duplicates:

```bash
# Manually clean crontab
crontab -l | grep -v run_pipeline | crontab -

# Then recreate
./scripts/outside_cron.sh 02:00
```

---

## Best Practices

### Recommended Schedules

| Use Case | Time | Reason |
|----------|------|--------|
| **Off-peak processing** | 02:00 - 04:00 | Minimal system load |
| **Morning report** | 08:00 | Data ready for morning review |
| **Evening batch** | 18:00 - 20:00 | Capture full day's data |

### Log Management

The log file grows over time. Set up log rotation:

```bash
# Add to /etc/logrotate.d/claw-agent
/home/sec-researchonly/Desktop/CLAW-Agent/cron_pipeline.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
}
```

Or manually clean old logs:

```bash
# Keep only last 7 days
find /home/sec-researchonly/Desktop/CLAW-Agent -name "cron_pipeline.log*" -mtime +7 -delete
```

### Monitoring

**Check if last run succeeded:**
```bash
# Look for "Pipeline Complete!" in logs
grep "Pipeline Complete!" cron_pipeline.log | tail -5
```

**Check for errors:**
```bash
grep -i "error" cron_pipeline.log | tail -20
```

**Set up alerting (optional):**
```bash
# Add to crontab to check for errors daily
0 9 * * * grep -i "error" /home/sec-researchonly/Desktop/CLAW-Agent/cron_pipeline.log | tail -10 | mail -s "CLAW-Agent Errors" your@email.com
```

---

## Related Scripts

- [`run_pipeline.sh`](./SCRIPTS_PIPELINE.md) - Main pipeline runner
- [`auto_run.sh`](./SCRIPTS_AUTO.md) - Alternative auto-run script
- [`clean_data.sh`](./SCRIPTS_CLEAN.md) - Clean old data files

---

## Quick Reference

```bash
# Set daily run at 2:00 AM
./scripts/outside_cron.sh 02:00

# Check status
./scripts/outside_cron.sh

# Remove cron job
./scripts/outside_cron.sh --remove

# View logs
tail -f cron_pipeline.log

# Verify crontab
crontab -l | grep run_pipeline
```

---

*For pipeline configuration details, see [CONFIGURATION.md](../config/CONFIGURATION.md).*