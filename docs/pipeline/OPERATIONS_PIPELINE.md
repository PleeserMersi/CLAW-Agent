# Pipeline Operations

Complete guide to running and operating the CLAW-Agent pipeline.

---

## Running the Pipeline

### Basic Execution

```bash
# Default run (2 days ago to 1 day ago, no filtering, batch sizes: 5/10/10/10/10, 4 workers)
./scripts/run_pipeline.sh

# With fault filtering enabled
./scripts/run_pipeline.sh --filter

# Custom date range
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-31

# Specific hall(s)
./scripts/run_pipeline.sh --halls hall_c
./scripts/run_pipeline.sh --halls hall_a hall_c

# Verbose logging
./scripts/run_pipeline.sh --verbose

# Skip SSH tunnel (if not needed or already established)
./scripts/run_pipeline.sh --no-tunnel

# Custom batch sizes and workers
./scripts/run_pipeline.sh --extract-size 10 --tag-size 20 --workers 8
```

### Full Command Reference

```bash
./scripts/run_pipeline.sh [OPTIONS]

Date Options:
  --start-date YYYY-MM-DD  Start date (default: 2 days ago)
  --end-date YYYY-MM-DD    End date (default: 1 day ago)

Pipeline Options:
  --verbose                Enable verbose logging (DEBUG level)
  --no-tunnel              Skip SSH tunnel creation
  --filter                 Enable fault filtering step (runs before tagging)
  --agent NAME             Agent for all pipeline stages (default: from .env)
  --extract-size N         Batch size for extraction (default: 5, None=no batching)
  --tag-size N             Batch size for tagging (default: 10)
  --filter-size N          Batch size for filtering (default: 10)
  --validation-size N      Batch size for verification (default: 10)
  --fixing-size N          Batch size for fixing (default: 10)
  --workers N              Number of parallel workers (default: 4)
  --halls HALL1 [HALL2...] Hall(s) to process (hall_a, hall_b, hall_c, hall_d)

Examples:
  ./run_pipeline.sh                           # Default: 2 days ago to 1 day ago
  ./run_pipeline.sh --filter                  # Enable fault filtering
  ./run_pipeline.sh --halls hall_c --filter   # Hall C with filtering
  ./run_pipeline.sh --extract-size 10         # Larger extraction batches
  ./run_pipeline.sh --verbose --workers 8     # Verbose + more parallelism
```

### Pipeline Stages

The pipeline executes in the following order:

1. **Data Loading**: Fetch shift summaries from JLab API (cached)
2. **Fault Extraction**: Extract faults using LLM (batched, parallel)
3. **Fault Filtering** (optional, `--filter`): Remove non-fault entries using LLM
4. **Tagging**: Classify faults into 16 categories (ChromaDB + LLM)
5. **Timestamp Verification**: Verify timestamps against summaries (15-min tolerance)
6. **Timestamp Fixing**: Correct inaccurate timestamps from full logbook entries
7. **Consolidation**: Merge accurate + fixed faults into final output

**Output Files Created**:
- `data/processed/extracted_faults.csv` - Faults after extraction + tagging
- `data/verified/accurate.csv` - Timestamps verified as accurate
- `data/verified/inaccurate.csv` - Timestamps needing correction
- `data/fixed/fixed.csv` - Successfully fixed timestamps
- `data/fixed/manual_check.csv` - Fixes needing manual review
- `data/final_output/all_shift_faults.csv` - Final merged output (appended each run)

---

## Common Workflows

### Daily Fault Analysis

```bash
# Run nightly (default dates, no filtering)
./scripts/run_pipeline.sh

# With fault filtering enabled
./scripts/run_pipeline.sh --filter

# View results
cat data/final_output/all_shift_faults.csv

# Check intermediate outputs
ls -la data/verified/
ls -la data/fixed/
```

### Historical Analysis

```bash
# Analyze entire month
./scripts/run_pipeline.sh \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --workers 8 \
  --extract-size 10
```

### Hall-Specific Report

```bash
# Hall C only
./scripts/run_pipeline.sh \
  --halls hall_c \
  --start-date 2024-01-01 \
  --end-date 2024-01-31
```

### Performance Testing

```bash
# Test with smaller batches (higher accuracy, slower)
./scripts/run_pipeline.sh --extract-size 5 --tag-size 5 --validation-size 5

# Test with larger batches (faster, may reduce accuracy)
./scripts/run_pipeline.sh --extract-size 20 --tag-size 20 --validation-size 20

# Test with more workers
./scripts/run_pipeline.sh --workers 8
./scripts/run_pipeline.sh --workers 12

# Combine batch size and worker tuning
./scripts/run_pipeline.sh --extract-size 10 --tag-size 15 --workers 8
```

---

## Scheduling

### Cron Job Example

Add to crontab (`crontab -e`):

```bash
# Run pipeline daily at 2 AM with filtering
0 2 * * * cd /home/sec-researchonly/Desktop/CLAW-Agent && ./scripts/run_pipeline.sh --filter >> logs/pipeline.log 2>&1

# Run without filtering (faster)
0 2 * * * cd /home/sec-researchonly/Desktop/CLAW-Agent && ./scripts/run_pipeline.sh >> logs/pipeline.log 2>&1
```

**Note**: Ensure SSH tunnel is available if JLab API requires it. Consider creating a separate cron job for tunnel setup.

### Systemd Timer

Create `/etc/systemd/system/claw-pipeline.service`:

```ini
[Unit]
Description=CLAW-Agent Pipeline
After=network.target

[Service]
Type=oneshot
User=sec-researchonly
WorkingDirectory=/home/sec-researchonly/Desktop/CLAW-Agent
ExecStart=/home/sec-researchonly/Desktop/CLAW-Agent/scripts/run_pipeline.sh --filter
Environment=HOME=/home/sec-researchonly
```

Create `/etc/systemd/system/claw-pipeline.timer`:

```ini
[Unit]
Description=Run CLAW-Agent Pipeline Daily

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl enable claw-pipeline.timer
sudo systemctl start claw-pipeline.timer
```

**Note**: Systemd services run in a minimal environment. Ensure `.env` file is accessible and SSH tunnels are pre-established if needed.

---

## Monitoring

### Log Files

**Pipeline logs**: Console output (redirect to file for persistence)

```bash
./scripts/run_pipeline.sh > logs/pipeline.log 2>&1
./scripts/run_pipeline.sh --verbose > logs/pipeline.log 2>&1  # DEBUG level
```

**Check progress**:
```bash
tail -f logs/pipeline.log
```

**Look for stage completion**:
```bash
grep "Step.*completed" logs/pipeline.log
grep "Pipeline Summary" logs/pipeline.log
```

### Output Monitoring

```bash
# Check if output was created
ls -lh data/final_output/

# Count faults (excluding header)
wc -l data/final_output/all_shift_faults.csv

# Check for errors in logs
grep -i "error" logs/pipeline.log

# Check stage timing
grep "completed in" logs/pipeline.log

# View pipeline summary
tail -20 logs/pipeline.log
```

---

### Data Folder Cleanup

**Before each run**, the pipeline automatically:
- Deletes all CSV and JSON files in `data/` (except `data/final_output/`)
- Preserves `all_shift_faults.csv` in `final_output/`

**To manually clean**:
```bash
# Remove all intermediate files (keeps final_output)
find data/ -type f \( -name "*.csv" -o -name "*.json" \) ! -path "data/final_output/*" -delete

# Or use the cleanup function via Python
python3 -c "from src.pipeline import _cleanup_data_folder; _cleanup_data_folder()"
```

**Note**: This cleanup happens automatically at pipeline start. No manual intervention needed.

### SSH Tunnel Issues

**Scenario**: Tunnel fails to establish

**Check**:
1. SSH credentials in `.env` (`SSH_USERNAME`, `SSH_HOST`)
2. Host reachable (`ping` or `ssh` test)
3. Local ports available (8000, 11435)

**Recovery**:
```bash
# Kill existing tunnel processes on configured ports
fuser -k 8000/tcp
fuser -k 11435/tcp

# Test SSH manually
ssh blankenship@137.155.253.88

# Check if ports are in use
fuser 8000/tcp
fuser 11435/tcp

# Re-run with --no-tunnel if SSH not needed
./scripts/run_pipeline.sh --no-tunnel
```

**Note**: If `SSH_USERNAME` or `SSH_HOST` is not configured, the pipeline skips tunnel setup automatically and logs a warning.

---

## Performance Tuning

### Batch Size Optimization

**Default batch sizes**: Extract=5, Tag=10, Filter=10, Validation=10, Fixing=10

**Trade-offs**:
- **Small batches** (1-5): Higher accuracy, more LLM calls, slower
- **Medium batches** (5-15): Balanced (default settings)
- **Large batches** (15-30): Faster, fewer LLM calls, may reduce accuracy

**Test different sizes**:
```bash
# Conservative (small batches)
./scripts/run_pipeline.sh --extract-size 3 --tag-size 5 --validation-size 5

# Balanced (default)
./scripts/run_pipeline.sh --extract-size 5 --tag-size 10 --validation-size 10

# Aggressive (large batches)
./scripts/run_pipeline.sh --extract-size 20 --tag-size 25 --validation-size 20

# Time comparison
for size in 5 10 20; do
  echo "Testing batch size $size"
  time ./scripts/run_pipeline.sh --extract-size $size --tag-size $size --validation-size $size
done
```

### Worker Count Optimization

**Default**: 4 workers

**Recommendations** (based on CPU cores):
- 4 cores: 4-5 workers
- 8 cores: 6-8 workers
- 16+ cores: 10-15 workers

**Note**: Since LLM calls are network-bound (not CPU-bound), increasing workers beyond CPU core count can still improve throughput. However, too many workers may cause:
- Rate limiting from LLM provider
- Memory pressure
- Diminishing returns

**Test**:
```bash
for workers in 2 4 6 8 12; do
  echo "Testing $workers workers"
  time ./scripts/run_pipeline.sh --workers $workers --extract-size 10
done
```

### Cache Utilization

**API Response Cache**: `CachedAPIClient` caches JLab API responses for 30 minutes (200 entry LRU cache)

**Benefit**: Repeated runs within 30 minutes use cached responses

**Strategy**: 
- Run multiple date ranges in sequence to maximize cache hits
- Cache is cleared when pipeline starts (cleanup step)
- For long historical runs, cache helps if overlapping date ranges

**Clear cache manually**:
```bash
python3 -c "from utils.cache_utils import CachedAPIClient; CachedAPIClient().clear_cache()"
```

---

## Troubleshooting

### "No data loaded"

**Check**:
1. Date range exists in JLab logbooks
2. Hall names are correct (hall_a, hall_b, hall_c, hall_d)
3. API credentials valid (`.env` file)

**Fix**:
```bash
# Test with known date range (recent dates)
./scripts/run_pipeline.sh --start-date 2024-04-01 --end-date 2024-04-03

# Check hall names
./scripts/run_pipeline.sh --halls hall_c --start-date 2024-04-01 --end-date 2024-04-03

# Enable verbose logging for more details
./scripts/run_pipeline.sh --verbose --start-date 2024-04-01 --end-date 2024-04-03
```

### "SSH tunnel failed"

**Check**:
1. SSH credentials in `.env`
2. Host reachable
3. Ports available

**Fix**:
```bash
# Test SSH
ssh blankenship@137.155.253.88

# Check ports
fuser 8000/tcp
fuser 11435/tcp
```

### "LLM call timeout"

**Check**:
1. OpenClaw running and accessible
2. Agent name correct (check `.env` `AGENT_NAME`)
3. Network connectivity to OpenClaw Gateway

**Fix**:
```bash
# Test OpenClaw agent
openclaw agent --agent fault_analyst --message "test"

# Check agent availability
openclaw status

# Try with different agent
./scripts/run_pipeline.sh --agent default

# Increase timeout (edit src/pipeline.py if needed)
# Find: timeout_seconds=300
# Change to: timeout_seconds=600
```

---

## Best Practices

### Daily Operations

1. Run pipeline nightly with default dates (2 days ago to 1 day ago)
2. Enable `--filter` flag for cleaner output
3. Monitor `logs/pipeline.log` for errors
4. Check `data/final_output/all_shift_faults.csv` daily
5. Review `data/fixed/manual_check.csv` weekly for manual fixes

### Weekly Maintenance

1. Review tag distribution: Check if any tags need updating
2. Update `tag_db/tags.json` if new fault patterns emerge
3. Archive old `all_shift_faults.csv` if file grows too large
4. Clear cache if stale data suspected

### Monthly Review

1. Analyze fault trends (dashboard or CSV analysis)
2. Review accuracy metrics (compare accurate vs fixed ratios)
3. Optimize batch sizes based on performance data
4. Update documentation with new findings

---

## Related Documentation

- [Configuration](./CONFIGURATION.md) - Settings reference
- [Quick Start](./QUICKSTART.md) - Getting started
- [Scripts](./SCRIPTS_PIPELINE.md) - Script reference

---

*For script details, see [SCRIPTS_PIPELINE.md](./SCRIPTS_PIPELINE.md).*