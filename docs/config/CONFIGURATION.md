# Configuration Reference

Complete guide to all configuration options in CLAW-Agent.

---

## Configuration Files

### `.env` (Environment Variables)

Primary configuration file. Copy from `.env.example`:

```bash
cp .env.example .env
```

---

## Environment Variables

### Required Variables

#### `JLAB_USERNAME`
- **Type**: String
- **Required**: Yes
- **Description**: Jefferson Lab logbook API username

#### `JLAB_PASSWORD`
- **Type**: String
- **Required**: Yes
- **Description**: Jefferson Lab logbook API password

---

### Optional Variables

#### `LOG_LEVEL`
- **Type**: String
- **Default**: `INFO`
- **Options**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Description**: Logging verbosity level

#### `OPENCLAW_PATH`
- **Type**: String
- **Default**: (empty)
- **Description**: Path to OpenClaw installation directory. If set, the project uses `openclaw` CLI. If **not set or empty**, the project uses **vLLM API directly** instead.
- **Example**: `/home/user/.npm-global/lib/node_modules/openclaw`

#### `AGENT_NAME`
- **Type**: String
- **Description**: OpenClaw agent name for LLM calls
- **Example**: `fault_analyst`

#### `VLLM_BASE_URL`
- **Type**: URL
- **Default**: `http://localhost:8000`
- **Description**: vLLM API endpoint URL (used when `OPENCLAW_PATH` is not set)

#### `VLLM_MODEL_NAME`
- **Type**: String
- **Default**: `qwen3-32b-local`
- **Description**: Model name to use for vLLM inference (used when `OPENCLAW_PATH` is not set)
- **Example**: `qwen3-122b-a10b`, `llama3-70b`

#### `VLLM_API_KEY`
- **Type**: String
- **Default**: (empty)
- **Description**: API key for vLLM endpoint if authentication is required (used when `OPENCLAW_PATH` is not set)

#### `OPENCLAW_CMD`
- **Type**: String
- **Default**: (auto-set based on `OPENCLAW_PATH`)
- **Description**: OpenClaw command path. Automatically set to `OPENCLAW_PATH` if `OPENCLAW_PATH` is set, otherwise `None`.
- **Note**: When `OPENCLAW_PATH` is not set, this is `None` and the project uses vLLM API directly.

---

### SSH Tunnel Configuration

#### `SSH_USERNAME`
- **Type**: String
- **Required for remote access**: Yes
- **Description**: SSH username

#### `SSH_HOST`
- **Type**: String (IP or hostname)
- **Required for remote access**: Yes
- **Description**: SSH server address

#### `SSH_TUNNEL_N_LOCAL`
- **Type**: Integer (port number)
- **Required if using tunnels**: Yes
- **Description**: Local port for tunnel N (N = 1, 2, 3...)
- **Example**: `SSH_TUNNEL_1_LOCAL=8000`

#### `SSH_TUNNEL_N_REMOTE`
- **Type**: Integer (port number)
- **Required if using tunnels**: Yes
- **Description**: Remote port for tunnel N
- **Example**: `SSH_TUNNEL_1_REMOTE=8001`

**Multiple Tunnels:**
```bash
SSH_TUNNEL_1_LOCAL=8000
SSH_TUNNEL_1_REMOTE=8001
SSH_TUNNEL_2_LOCAL=11435
SSH_TUNNEL_2_REMOTE=11434
```

---

### Dashboard Server Configuration

#### `DASHBOARD_SSH_USERNAME`
- **Type**: String
- **Description**: SSH username for dashboard deployment server

#### `DASHBOARD_SSH_HOST`
- **Type**: String
- **Description**: SSH host for dashboard server

#### `DASHBOARD_SSH_PORT`
- **Type**: Integer
- **Default**: `22`
- **Description**: SSH port for dashboard server

#### `DASHBOARD_REMOTE_PORT`
- **Type**: Integer
- **Default**: `3335`
- **Description**: Remote port for dashboard service

---

## Hardcoded Configuration (`config.py`)

These values are defined in `src/config.py` and typically don't need modification.

### Base Directories

```python
BASE_DIR = Path(__file__).parent.parent  # Project root
DATA_DIR = BASE_DIR / "data"
SRC_DIR = BASE_DIR / "src"

RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FINAL_OUTPUT_DIR = DATA_DIR / "final_output"
VERIFIED_DIR = DATA_DIR / "verified"
FIXED_DIR = DATA_DIR / "fixed"
```

### File Paths

```python
SHIFT_SUMMARY_JSON = RAW_DIR / "shift_summary.JSON"
SHIFT_SUMMARY_CSV = RAW_DIR / "shift_summary.csv"
PROCESSED_SUMMARIES_CSV = PROCESSED_DIR / "processed_summaries.csv"
ALL_FAULTS_CSV = FINAL_OUTPUT_DIR / "all_shift_faults.csv"
NOT_FAULTS_CSV = PROCESSED_DIR / "not_faults.csv"
ACCURATE_CSV = VERIFIED_DIR / "accurate.csv"
INACCURATE_CSV = VERIFIED_DIR / "inaccurate.csv"
FIXED_CSV = FIXED_DIR / "fixed.csv"
MANUAL_CHECK_CSV = FINAL_OUTPUT_DIR / "manual_check.csv"
```

### API Configuration

```python
JLAB_LOGBOOK_BASE_URL = "https://logbooks.jlab.org/api/elog"

HALL_LOGBOOKS = {
    "hall_a": "halog",      # Main Hall A Operational Logbook
    "hall_b": "hblog",      # Main Hall B Operational Logbook
    "hall_c": "hclog",      # Main Hall C Operational Logbook
    "hall_d": "hdlog",      # Main Hall D Operational Logbook
}

DEFAULT_HALLS = list(HALL_LOGBOOKS.keys())  # ['hall_a', 'hall_b', 'hall_c', 'hall_d']
EXCLUDED_LOGBOOKS = ["-3", "-5"]
SEARCH_TITLE = "Shift Summary"
DEFAULT_PAGE_LIMIT = 50
API_DELAY_SECONDS = 0.5  # Delay between API calls to avoid rate limiting
```

### Verification Thresholds

```python
TIMESTAMP_TOLERANCE_MINUTES = 15  # Acceptable timestamp deviation
```

---

## Configuration Validation

### Automatic Validation

Run validation before pipeline starts:

```python
from config import validate_config, validate_config_strict

# Returns list of warnings/errors
issues = validate_config()

# Raises ValueError on critical errors
validate_config_strict()
```

### Validation Checks

1. **Base Directory**: Exists
2. **Data Directories**: Exist and writable
3. **Authentication**: Username/password set
4. **Agent Configuration**: AGENT_NAME not empty
5. **OpenClaw Command**: OPENCLAW_CMD set
6. **SSH Configuration**: Username/host match
7. **Tunnel Configuration**: Port pairs complete
8. **API URL**: Uses HTTPS
9. **Numeric Parameters**: Positive values

### Common Validation Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `JLAB_USERNAME not set` | Missing env var | Add to `.env` |
| `JLAB_PASSWORD not set` | Missing env var | Add to `.env` |
| `AGENT_NAME is empty`   | Empty value | Set valid agent name |
| `No write permission`   | Directory permissions | `chmod 755 data/` |
| `Incomplete SSH tunnel` | Missing port pair | Add both LOCAL and REMOTE |

---

## Hall Configuration

### Available Halls

| Hall ID | Logbook ID | Description |
|---------|------------|-------------|
| `hall_a` | `halog` | Hall A Operational Logbook |
| `hall_b` | `hblog` | Hall B Operational Logbook |
| `hall_c` | `hclog` | Hall C Operational Logbook |
| `hall_d` | `hdlog` | Hall D Operational Logbook |

### Processing Specific Halls

**Command Line:**
```bash
./scripts/run_pipeline.sh --halls hall_c
./scripts/run_pipeline.sh --halls hall_a hall_b hall_c
```

**Environment (default):**
All halls are processed by default. To change default, edit `config.py`:

```python
DEFAULT_HALLS = ["hall_c"]  # Only process Hall C
```

---

## Batch Size Configuration

Batch sizes control how many items are processed per LLM call.

### Available Batch Sizes

| Parameter | Default | Description | Stage |
|-----------|---------|-------------|-------|
| `extract_size` | 5 | Summaries per batch | Fault Extraction |
| `tag_size` | 10 | Faults per batch | Tagging |
| `filter_size` | 10 | Faults per batch | Filtering |
| `validation_size` | 10 | Faults per batch | Verification |
| `fixing_size` | 10 | Faults per batch | Fixing |

### Setting Batch Sizes

**Command Line:**
```bash
./scripts/run_pipeline.sh \
  --extract-size 10 \
  --tag-size 20 \
  --filter-size 15 \
  --validation-size 15 \
  --fixing-size 10
```

**Environment (permanent):**
Edit `scripts/run_pipeline.sh`:

```bash
# Change defaults
EXTRACT_SIZE="--extract-size 10"
TAG_SIZE="--tag-size 20"
```

### Batch Size Trade-offs

| Size | Speed | Accuracy | Memory |
|------|-------|----------|--------|
| Small (1-5) | Slow | High | Low |
| Medium (5-15) | Medium | Medium | Medium |
| Large (15-30) | Fast | Variable | High |

**Recommendations:**
- **Start with defaults** (5-10)
- **Increase for speed** if accuracy is acceptable
- **Decrease for accuracy** if errors occur
- **Monitor LLM token usage** for cost optimization

---

## Worker Pool Configuration

### Parallel Workers

**Parameter**: `--workers` or `-w`

**Default**: 5

**Range**: 1-50 (practical limit depends on system)

**Command Line:**
```bash
./scripts/run_pipeline.sh --workers 8
```

### Worker Recommendations

| System | Workers | Notes |
|--------|---------|-------|
| Laptop (4 cores) | 4-5 | Balanced |
| Desktop (8 cores) | 6-8 | Optimal |
| Server (16+ cores) | 10-15 | High throughput |
| Resource-constrained | 2-3 | Low memory |

**Trade-offs:**
- **More workers**: Faster completion, higher memory usage
- **Fewer workers**: Slower, lower resource usage
- **Too many**: Diminishing returns, context switching overhead

---

## Date Range Configuration

### Date Format

**Format**: `YYYY-MM-DD`

**Examples**:
- `2024-01-01` (January 1, 2024)
- `2024-12-31` (December 31, 2024)

### Default Date Range

**Script Default**: 2 days ago to 1 day ago

```bash
START_DATE=$(date -d "2 days ago" +%Y-%m-%d)
END_DATE=$(date -d "1 day ago" +%Y-%m-%d)
```

### Setting Date Ranges

**Command Line:**
```bash
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-31
```

**Validation:**
- Start date must be before end date
- Both dates must be valid YYYY-MM-DD format
- Future dates will return no results

---

## Logging Configuration

### Log Levels

| Level | Value | Description |
|-------|-------|-------------|
| DEBUG | 10 | Detailed diagnostic information |
| INFO | 20 | General progress updates |
| WARNING | 30 | Non-critical issues |
| ERROR | 40 | Critical errors |

### Setting Log Level

**Environment:**
```bash
LOG_LEVEL=DEBUG
```

**Command Line:**
```bash
./scripts/run_pipeline.sh --verbose  # Sets DEBUG level
```

### Log Output

**Console**: Standard output with timestamps

```
2024-01-15 14:30:45 - CLAW-Agent - INFO - Starting pipeline
2024-01-15 14:30:46 - CLAW-Agent - DEBUG - API call completed
```

**File** (optional): Configured in `logging_utils.py`

---

## SSH Tunnel Configuration Details

### When to Use Tunnels

**Use SSH tunnel when:**
- JLab API is only accessible from internal network
- vLLM instance is on external machine
- Direct internet access is blocked

**Skip tunnel when:**
- Running on JLab internal network
- API is publicly accessible
- Using local vLLM instance

### Tunnel Setup

**Example Configuration:**
```bash
SSH_USERNAME=blankenship
SSH_HOST=137.155.253.88
SSH_TUNNEL_1_LOCAL=8000
SSH_TUNNEL_1_REMOTE=8001
SSH_TUNNEL_2_LOCAL=11435
SSH_TUNNEL_2_REMOTE=11434
```

**What Happens:**
1. SSH connection established to `blankenship@137.155.253.88`
2. Local port 8000 forwards to remote port 8001 (Tunnel 1)
3. Local port 11435 forwards to remote port 11434 (Tunnel 2)
4. Pipeline uses `localhost:8000` and `localhost:11435`

### Troubleshooting Tunnels

**Tunnel fails to start:**
```bash
# Test SSH manually
ssh blankenship@137.155.253.88

# Check port availability
fuser 8000/tcp
fuser 11435/tcp

# Kill existing processes
fuser -k 8000/tcp
fuser -k 11435/tcp
```

**Connection refused:**
- Verify SSH credentials
- Check firewall rules
- Confirm remote ports are correct

---

## Custom Configuration Examples

### Minimal Configuration (Local Testing)

```bash
# .env
JLAB_USERNAME=test_user
JLAB_PASSWORD=test_password
AGENT_NAME=test_agent
LOG_LEVEL=DEBUG

# No SSH tunnel (local API access)
```

### Production Configuration (Remote Access)

```bash
# .env
JLAB_USERNAME=prod_user
JLAB_PASSWORD=secure_password
AGENT_NAME=fault_analyst
LOG_LEVEL=INFO

SSH_USERNAME=prod_ssh_user
SSH_HOST=137.155.253.88
SSH_TUNNEL_1_LOCAL=8000
SSH_TUNNEL_1_REMOTE=8001
SSH_TUNNEL_2_LOCAL=11435
SSH_TUNNEL_2_REMOTE=11434

DASHBOARD_SSH_USERNAME=prod_ssh_user
DASHBOARD_SSH_HOST=137.155.253.88
DASHBOARD_SSH_PORT=22
DASHBOARD_REMOTE_PORT=3335
```

### High-Performance Configuration

```bash
# .env
JLAB_USERNAME=prod_user
JLAB_PASSWORD=secure_password
AGENT_NAME=fault_analyst
LOG_LEVEL=WARNING  # Less logging overhead

# Large batch sizes
# Set in run_pipeline.sh:
# --extract-size 20 --tag-size 30 --validation-size 25
# --workers 12
```

---

## Configuration Best Practices

### Security

1. **Never commit `.env`** to version control
2. **Use strong passwords** for JLab API
3. **Rotate credentials** periodically
4. **Limit SSH key permissions** (`chmod 600`)
5. **Use HTTPS** for all API endpoints

### Performance

1. **Tune batch sizes** based on LLM response times
2. **Adjust worker count** for your CPU cores
3. **Enable caching** (default, don't disable)
4. **Use appropriate log level** (INFO for production)
5. **Process smaller date ranges** for faster runs

### Reliability

1. **Validate config** before long runs
2. **Test with small date range** first
3. **Monitor disk space** for output files
4. **Set reasonable timeouts** for LLM calls
5. **Enable verbose logging** for debugging

---

## Troubleshooting Configuration Issues

### "Configuration validation failed"

**Check:**
1. All required env vars are set
2. No typos in variable names
3. Values are in correct format
4. Directories exist and are writable

**Fix:**
```bash
# Validate configuration
python3 -c "from config import validate_config_strict; validate_config_strict()"

# Check specific values
python3 -c "from config import *; print(f'Halls: {DEFAULT_HALLS}')"
```

### "SSH tunnel failed"

**Check:**
1. SSH credentials are correct
2. Host is reachable (`ping SSH_HOST`)
3. Ports are available locally
4. SSH server accepts connections

**Fix:**
```bash
# Test SSH connection
ssh -v SSH_USERNAME@SSH_HOST

# Check tunnel ports
lsof -i :8000
lsof -i :11435
```

### "No data loaded"

**Check:**
1. Date range exists in JLab logbooks
2. Hall names are correct
3. API credentials are valid
4. Network connectivity to JLab

**Fix:**
```bash
# Test API manually
curl -u JLAB_USERNAME:JLAB_PASSWORD \
  "https://logbooks.jlab.org/api/elog/entries?startdate=2024-01-01&enddate=2024-01-02"
```

---

## Configuration Reference Summary

| Variable | Type | Default | Required | Description |
|----------|------|---------|----------|-------------|
| `JLAB_USERNAME` | String | - | Yes | JLab API username |
| `JLAB_PASSWORD` | String | - | Yes | JLab API password |
| `AGENT_NAME` | String | `fault_analyst` | Yes | OpenClaw agent (used only with openclaw CLI) |
| `LOG_LEVEL` | String | `INFO` | No | Logging verbosity |
| `OPENCLAW_PATH` | String | (empty) | No | OpenClaw installation path (if not set, uses vLLM API) |
| `OPENCLAW_CMD` | String | (auto) | No | OpenClaw command (auto-set from OPENCLAW_PATH) |
| `VLLM_BASE_URL` | URL | `http://localhost:8000` | No | vLLM API endpoint (used when OPENCLAW_PATH not set) |
| `VLLM_MODEL_NAME` | String | `qwen3-32b` | No | vLLM model name (used when OPENCLAW_PATH not set) |
| `VLLM_API_KEY` | String | (empty) | No | vLLM API key (optional) |
| `SSH_USERNAME` | String | - | No | SSH username |
| `SSH_HOST` | String | - | No | SSH host |
| `SSH_TUNNEL_N_LOCAL` | Int | - | No | Local tunnel port |
| `SSH_TUNNEL_N_REMOTE` | Int | - | No | Remote tunnel port |

---

*For usage examples, see [QUICKSTART.md](./QUICKSTART.md) and [OPERATIONS_PIPELINE.md](./OPERATIONS_PIPELINE.md).*