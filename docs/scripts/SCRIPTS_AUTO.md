# Auto-Run Scheduler

Reference for `scripts/auto_run.sh`.

---

## Overview

**Daily scheduler** that runs the CLAW-Agent pipeline once per day at a configurable time until manually stopped. Includes robust error handling, retry logic, and comprehensive logging.

**Location**: `scripts/auto_run.sh`

**Key Features**:
- Runs pipeline daily at scheduled time (default: 12:00 PM)
- Automatic date calculation (2 days ago → 1 day ago)
- Retry logic with exponential backoff
- Comprehensive logging to file and console
- Graceful shutdown handling (Ctrl+C, signals)
- Stop file support for remote termination

---

## Usage

```bash
./scripts/auto_run.sh [OPTIONS]
```

---

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--start-time HH:MM` | Schedule time in 24-hour format | `12:00` |
| `--agent NAME` | Pass agent name to pipeline | (none) |
| `--max-retries N` | Max retries on failure | `3` |
| `--log-file PATH` | Custom log file path | `logs/auto_run.log` |
| `--help` | Show help message | - |

---

## Examples

### Start Daily Scheduler (Noon)

```bash
./scripts/auto_run.sh
```

Runs pipeline daily at 12:00 PM with default settings.

### Custom Schedule Time

```bash
./scripts/auto_run.sh --start-time 14:00
```

Runs pipeline daily at 2:00 PM.

### With Specific Agent

```bash
./scripts/auto_run.sh --agent fault_analyst
```

Passes `--agent fault_analyst` to the pipeline on each run.

### Custom Retry Count

```bash
./scripts/auto_run.sh --max-retries 5
```

Retries up to 5 times on failure with exponential backoff.

### Custom Log File

```bash
./scripts/auto_run.sh --log-file /var/log/claw/auto_run.log
```

---

## Date Calculation

The script automatically calculates the date range for each run:

- **Start Date**: 2 days ago (`date -d "2 days ago"`)
- **End Date**: 1 day ago (`date -d "1 day ago"`)

This ensures the pipeline always processes the previous day's shifts.

---

## Retry Logic

**Exponential Backoff**:
- Attempt 1 fails → Wait 60s (1² × 60)
- Attempt 2 fails → Wait 240s (2² × 60)
- Attempt 3 fails → Wait 540s (3² × 60)

If all retries fail, the scheduler waits until the next scheduled day.

---

## Logging

**Log Format**:
```
[YYYY-MM-DD HH:MM:SS] [LEVEL] Message
```

**Log Levels**:
- `INFO` - Normal operational messages
- `WARN` - Warnings (shutdown requests, retries)
- `ERROR` - Errors (pipeline failures)

**Default Log Location**: `logs/auto_run.log`

**Sample Log Output**:
```
[2026-07-17 12:00:00] [INFO] ==========================================
[2026-07-17 12:00:00] [INFO] CLAW-Agent Auto-Runner Started
[2026-07-17 12:00:00] [INFO] Configuration:
[2026-07-17 12:00:00] [INFO]   Schedule: Daily at 12:00
[2026-07-17 12:00:00] [INFO]   Max Retries: 3
[2026-07-17 12:00:00] [INFO]   Log File: /home/user/CLAW-Agent/logs/auto_run.log
[2026-07-17 12:00:00] [INFO] Waiting for scheduled time...
[2026-07-17 12:00:01] [INFO] ==========================================
[2026-07-17 12:00:01] [INFO] Scheduled Pipeline Run - Date Range: 2026-07-15 to 2026-07-16
[2026-07-17 12:00:01] [INFO] Pipeline command: bash scripts/run_pipeline.sh --start-date 2026-07-15 --end-date 2026-07-16
[2026-07-17 12:05:30] [INFO] Pipeline completed successfully on attempt 1!
```

---

## Shutdown Handling

**Stop Methods**:

1. **Ctrl+C** (SIGINT)
   ```bash
   Ctrl+C
   ```

2. **Stop File** (for remote termination)
   ```bash
   touch CLAW-Agent/.stop_scheduler
   ```

3. **Kill Signal** (SIGTERM)
   ```bash
   kill <pid>
   ```

**Graceful Shutdown**:
- Current pipeline run completes (if in progress)
- Scheduler logs shutdown message
- Process exits cleanly

---

## Implementation Details

### Main Loop

1. **Wait for scheduled time** (checks every 60 seconds)
2. **Run pipeline** with retry logic
3. **Wait 24 hours** (checks stop file every 30 seconds)
4. **Repeat** until stopped

### Error Handling

- **Pipeline failures**: Retry with exponential backoff
- **Script failures**: Scheduler continues (doesn't exit on error)
- **Time calculation**: Uses `date -d` for portable date arithmetic
- **Log directory**: Auto-creates if missing

---

## Monitoring

### Check Scheduler Status

```bash
# Find running scheduler
grep -p auto_run.sh /proc/*/cmdline 2>/dev/null | cut -d/ -f3 | sort -u

# View recent logs
tail -f logs/auto_run.log

# Check for stop file
ls -la .stop_scheduler
```

### Stop Scheduler

```bash
# Method 1: Ctrl+C (if running in terminal)
# Method 2: Create stop file
touch .stop_scheduler

# Method 3: Kill process
pkill -f auto_run.sh
```

---

## Related Documentation

- [Pipeline Runner](./SCRIPTS_PIPELINE.md) - Main runner script
- [Operations](../pipeline/OPERATIONS_PIPELINE.md) - Pipeline operations
- [Configuration](../config/CONFIGURATION.md) - Pipeline configuration

---

*For main runner details, see [SCRIPTS_PIPELINE.md](./SCRIPTS_PIPELINE.md).*
