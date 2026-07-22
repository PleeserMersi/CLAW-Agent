# Pipeline Runner Script

Reference for `scripts/run_pipeline.sh`.

---

## Overview

Main entry point for running the CLAW-Agent fault extraction pipeline. Handles virtual environment setup, dependency installation, date calculation, and passes configuration to the Python pipeline.

**Location**: `scripts/run_pipeline.sh`

**Key Features**:
- Automatic virtual environment creation and activation
- Dependency installation from `requirements.txt`
- Default date range: 2 days ago → 1 day ago
- Configurable batch sizes for each pipeline stage
- Hall filtering support
- Verbose logging option
- SSH tunnel bypass option

---

## Usage

```bash
./scripts/run_pipeline.sh [OPTIONS]
```

---

## Options

### Date Options

| Option | Default | Description |
|--------|---------|-------------|
| `--start-date YYYY-MM-DD` | 2 days ago | Pipeline start date |
| `--end-date YYYY-MM-DD` | 1 day ago | Pipeline end date |

### Pipeline Options

| Option | Default | Description |
|--------|---------|-------------|
| `--verbose` | Off | Enable verbose logging |
| `--no-tunnel` | Off | Skip SSH tunnel creation |
| `--filter` | Off | Enable fault filtering step |
| `--agent NAME` | (none) | Agent name for all stages |
| `--extract-size N` | 5 | Batch size for extraction |
| `--tag-size N` | 10 | Batch size for tagging |
| `--filter-size N` | 10 | Batch size for filtering |
| `--validation-size N` | 10 | Batch size for verification |
| `--fixing-size N` | 10 | Batch size for fixing |
| `--halls HALL1 [HALL2...]` | All | Process specific halls |

### Help

| Option | Description |
|--------|-------------|
| `--help` | Show help message and exit |

---

## Valid Hall Names

---

## Cron Scheduling Script

For automated daily execution, use the companion script `outside_cron.sh`:

**Location**: `scripts/outside_cron.sh`

**Purpose**: Create, update, or remove a daily cron job to run the pipeline automatically.

### Usage

```bash
# Create daily cron job at 2:00 AM
./scripts/outside_cron.sh 02:00

# Create daily cron job at 6:30 PM
./scripts/outside_cron.sh 18:30

# Show current cron status
./scripts/outside_cron.sh

# Remove the cron job
./scripts/outside_cron.sh --remove
```

### Features

- **Time validation**: Ensures HH:MM format (24-hour)
- **Idempotent**: Updates existing cron job if one already exists
- **Logging**: Pipeline output goes to `cron_pipeline.log` in project root
- **Safe**: Preserves other crontab entries, only removes CLAW-Agent related jobs
- **Shows status**: Displays current cron schedule when run without arguments

### Example Output

```bash
$ ./scripts/outside_cron.sh 02:00
✓ Cron job created successfully!

Schedule: Daily at 02:00
Script: /home/sec-researchonly/Desktop/CLAW-Agent/scripts/run_pipeline.sh
Log file: /home/sec-researchonly/Desktop/CLAW-Agent/cron_pipeline.log

Current crontab:
  0 2 * * * cd /home/sec-researchonly/Desktop/CLAW-Agent && /home/sec-researchonly/Desktop/CLAW-Agent/scripts/run_pipeline.sh >> /home/sec-researchonly/Desktop/CLAW-Agent/cron_pipeline.log 2>&1
```

### Log File

The cron job writes all output to `cron_pipeline.log`:
```bash
# View recent logs
tail -f cron_pipeline.log

# Search for errors
grep -i error cron_pipeline.log
```

### Use Cases

1. **Daily automated processing**: Schedule pipeline to run every night
2. **Off-peak execution**: Run during low-usage hours (e.g., 2:00 AM)
3. **Consistent data extraction**: Ensure daily faults are captured without manual intervention

---

## Valid Hall Names

- `hall_a` - Hall A
- `hall_b` - Hall B
- `hall_c` - Hall C
- `hall_d` - Hall D

Multiple halls can be specified:
```bash
--halls hall_a hall_c
```

---

## Examples

### Default Run (Yesterday's Data)

```bash
./scripts/run_pipeline.sh
```

**What happens**:
- Start date: 2 days ago
- End date: 1 day ago
- All halls processed
- Default batch sizes used
- Fault filtering disabled
- Verbose logging off

**Sample output**:
```
==========================================
CLAW-Agent Pipeline Runner
==========================================

Configuration:
  Start date: 2026-07-15
  End date:   2026-07-16
  Verbose:    no
  No tunnel:  no
  Filter:     no

Running pipeline...
==========================================

Command: python3 src/pipeline.py --start-date 2026-07-15 --end-date 2026-07-16 --extract-size 5 --tag-size 10 --filter-size 10 --validation-size 10 --fixing-size 10

[Pipeline execution starts...]
```

### Custom Date Range

```bash
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-31
```

Processes all shifts from January 2024.

### Hall-Specific Processing

```bash
# Single hall
./scripts/run_pipeline.sh --halls hall_c

# Multiple halls
./scripts/run_pipeline.sh --halls hall_a hall_c

# Hall with custom dates
./scripts/run_pipeline.sh --halls hall_b --start-date 2024-01-01 --end-date 2024-01-15
```

### Enable Fault Filtering

```bash
./scripts/run_pipeline.sh --filter
```

Runs the optional fault filtering stage using LLM validation.

### Verbose Logging

```bash
./scripts/run_pipeline.sh --verbose
```

Enables detailed logging for debugging and monitoring.

### Custom Batch Sizes

```bash
./scripts/run_pipeline.sh \
  --extract-size 10 \
  --tag-size 20 \
  --filter-size 15 \
  --validation-size 15 \
  --fixing-size 10
```

**Performance impact**:
- Larger batches = faster processing but more memory usage
- Smaller batches = slower but more memory-efficient
- Recommended: extraction=5-10, others=10-20

### Skip SSH Tunnel

```bash
./scripts/run_pipeline.sh --no-tunnel
```

Use when JLab API is accessible directly (no SSH tunnel needed).

### With Specific Agent

```bash
./scripts/run_pipeline.sh --agent fault_analyst
```

Uses the specified agent for all pipeline stages.

### Complex Example

```bash
./scripts/run_pipeline.sh \
  --start-date 2024-06-01 \
  --end-date 2024-06-30 \
  --halls hall_a hall_c \
  --filter \
  --verbose \
  --extract-size 8 \
  --tag-size 15 \
  --agent my_agent
```

Processes June 2024 data for Halls A and C, with filtering enabled, verbose logging, and custom batch sizes.

---

## Virtual Environment Management

### Automatic Setup

The script automatically handles the virtual environment:

1. **Check for existing venv**:
   ```bash
   if [ -f "$VENV_DIR/bin/activate" ]; then
       echo "Activating virtual environment..."
       source "$VENV_DIR/bin/activate"
   ```

2. **Create if missing**:
   ```bash
   else
       echo "Virtual environment not found. Creating..."
       python3 -m venv "$VENV_DIR"
       source "$VENV_DIR/bin/activate"
       
       echo "Installing dependencies..."
       pip install --upgrade pip
       pip install -r requirements.txt
   ```

3. **Activate**:
   - Uses existing venv or creates new one
   - Installs all dependencies from `requirements.txt`
   - Proceeds with pipeline execution

### Manual venv Management

```bash
# Create manually
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Then run pipeline
./scripts/run_pipeline.sh
```

### Reinstall Dependencies

```bash
# Remove and recreate
rm -rf venv
./scripts/run_pipeline.sh  # Will recreate venv
```

---

## Default Date Calculation

```bash
START_DATE=$(date -d "2 days ago" +%Y-%m-%d)
END_DATE=$(date -d "1 day ago" +%Y-%m-%d)
```

**Examples** (running on 2026-07-17):
- `START_DATE` = 2026-07-15
- `END_DATE` = 2026-07-16

**Why 2 days ago to 1 day ago?**
- Ensures complete day data (not partial current day)
- Allows time for logbook entries to be finalized
- Typical daily batch processing window

---

## Command Construction

The script builds the Python command dynamically:

```bash
# Base command
CMD="python3 src/pipeline.py"
CMD="$CMD --start-date $START_DATE --end-date $END_DATE"

# Default batch sizes (if not overridden)
[ -z "$EXTRACT_SIZE" ] && EXTRACT_SIZE="--extract-size 5"
[ -z "$TAG_SIZE" ] && TAG_SIZE="--tag-size 10"
[ -z "$FILTER_SIZE" ] && FILTER_SIZE="--filter-size 10"
[ -z "$VALIDATION_SIZE" ] && VALIDATION_SIZE="--validation-size 10"
[ -z "$FIXING_SIZE" ] && FIXING_SIZE="--fixing-size 10"

# Add optional flags
[ -n "$VERBOSE" ] && CMD="$CMD $VERBOSE"
[ -n "$NO_TUNNEL" ] && CMD="$CMD $NO_TUNNEL"
[ -n "$FILTER" ] && CMD="$CMD $FILTER"
[ -n "$AGENT" ] && CMD="$CMD $AGENT"
CMD="$CMD $EXTRACT_SIZE $TAG_SIZE $FILTER_SIZE $VALIDATION_SIZE $FIXING_SIZE"
[ -n "$HALLS" ] && CMD="$CMD $HALLS"

# Execute
eval $CMD
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Pipeline completed successfully |
| 1 | General error (invalid args, pipeline failure) |
| 130 | Interrupted by Ctrl+C (SIGINT) |

**Note**: Script uses `set -e` which causes immediate exit on any command failure.

---

## Error Handling

### Missing Arguments

```bash
./scripts/run_pipeline.sh --start-date
# Error: shift 2 fails when argument missing
```

### Invalid Hall Name

Script passes invalid hall names to Python pipeline, which validates them.

### Virtual Environment Issues

```bash
# Permission denied
chmod +x scripts/run_pipeline.sh

# Python not found
export PATH="/usr/local/bin:$PATH"
```

### Dependency Installation Failure

```bash
# Check Python version (requires 3.8+)
python3 --version

# Manual dependency install
source venv/bin/activate
pip install -r requirements.txt
```

---

## Troubleshooting

### Pipeline Won't Start

1. **Check script is executable**:
   ```bash
   chmod +x scripts/run_pipeline.sh
   ```

2. **Verify Python3 is available**:
   ```bash
   which python3
   python3 --version  # Should be 3.8+
   ```

3. **Check .env file exists**:
   ```bash
   ls -la .env
   ```

### Wrong Date Range

```bash
# Debug: see calculated dates
START_DATE=$(date -d "2 days ago" +%Y-%m-%d)
END_DATE=$(date -d "1 day ago" +%Y-%m-%d)
echo "Start: $START_DATE, End: $END_DATE"

# Override with explicit dates
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-02
```

### Hall Not Processing

```bash
# Verify hall names (lowercase with underscore)
./scripts/run_pipeline.sh --halls hall_a
./scripts/run_pipeline.sh --halls hall_b hall_c

# Check hall exists in config
# See TAG_DATABASE.md for valid hall names
```

### Batch Size Too Large

```bash
# Reduce batch sizes for memory issues
./scripts/run_pipeline.sh \
  --extract-size 3 \
  --tag-size 5 \
  --filter-size 5
```

### SSH Tunnel Issues

```bash
# If SSH tunnel is not needed
./scripts/run_pipeline.sh --no-tunnel

# If tunnel is required but not configured
# See ENVIRONMENT.md for SSH tunnel setup
```

---

## Performance Tuning

### Optimal Batch Sizes

| Stage | Small | Medium | Large |
|-------|-------|--------|-------|
| Extraction | 3 | 5 | 10 |
| Tagging | 5 | 10 | 20 |
| Filtering | 5 | 10 | 20 |
| Validation | 5 | 10 | 20 |
| Fixing | 5 | 10 | 20 |

**Memory usage**: Larger batches consume more RAM during parallel processing.

**Speed vs. Quality**: Larger batches may slightly reduce accuracy but significantly improve speed.

### Parallel Workers

Note: Worker count is configured in `src/pipeline.py` and `config.py`, not via this script.

---

## Related Documentation

- [Operations](../pipeline/OPERATIONS_PIPELINE.md) - Pipeline operations guide
- [Configuration](../config/CONFIGURATION.md) - Pipeline configuration
- [Environment](../config/ENVIRONMENT.md) - Environment variables
- [Quick Start](../getting-started/QUICKSTART.md) - Getting started

---

*For detailed pipeline operations, see [OPERATIONS_PIPELINE.md](../pipeline/OPERATIONS_PIPELINE.md).*