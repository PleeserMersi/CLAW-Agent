# Quick Start Guide

Get CLAW-Agent up and running in 5 minutes.

---

## Prerequisites

- Python 3.8+
- **Either**:
  - OpenClaw installed and configured (`openclaw` command available), **OR**
  - Access to a vLLM server with the desired model
- JLab logbook API credentials (for fetching shift summaries)
- SSH access (optional, for remote access or dashboard deployment)

---

## Step 1: Clone/Navigate to Project

```bash
cd CLAW-Agent
```

---

## Step 2: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required settings in `.env`:**

```bash
# JLab Logbook API (for fetching shift summaries)
JLAB_USERNAME=your_jlab_username
JLAB_PASSWORD=your_jlab_password

# LLM Configuration - Choose ONE mode:
# MODE A: OpenClaw CLI (recommended if OpenClaw is installed)
AGENT_NAME=your_openclaw_agent_name
OPENCLAW_PATH=/path/to/openclaw  # e.g., ~/.npm-global/lib/node_modules/openclaw

# MODE B: Direct vLLM API (leave OPENCLAW_PATH empty)
# VLLM_BASE_URL=http://localhost:8000
# VLLM_MODEL_NAME=qwen3-32b
# VLLM_API_KEY=  # optional

# Logging Level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# Optional: SSH Tunnel (for remote JLab access)
# Format: SSH_TUNNEL_N_LOCAL=<local_port> and SSH_TUNNEL_N_REMOTE=<remote_port>
SSH_USERNAME=your_ssh_username
SSH_HOST=your_ssh_host
SSH_TUNNEL_1_LOCAL=8000
SSH_TUNNEL_1_REMOTE=8000

# Optional: Dashboard deployment server (leave empty to run locally)
DASHBOARD_SSH_USERNAME=
DASHBOARD_SSH_HOST=
DASHBOARD_SSH_PORT=
DASHBOARD_REMOTE_PORT=
```

---

## Step 3: Install Dependencies

The pipeline runner will auto-install dependencies if needed:

```bash
# Option 1: Let the script handle it
./scripts/run_pipeline.sh --help

# Option 2: Manual installation
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Dependencies installed:**
- pandas>=2.0.0
- numpy>=1.24.0
- requests>=2.31.0
- beautifulsoup4>=4.12.0
- pydantic>=2.0.0
- streamlit>=1.28.0
- plotly>=5.17.0
- chromadb>=0.5.0
- sentence-transformers>=3.0.0
- python-dotenv>=1.0.0
- matplotlib>=3.10.0

---

## Step 4: Verify Setup

**If using OpenClaw mode:**
```bash
# Check OpenClaw is available
which openclaw

# List available agents
openclaw agent --list
```

**If using vLLM mode:**
```bash
# Test vLLM API connectivity
curl http://localhost:8000/v1/models
```

---

## Step 5: Run Your First Pipeline

### Default Run (Last 2 Days)

```bash
./scripts/run_pipeline.sh
```

This runs:
- **Start Date**: 2 days ago (auto-calculated)
- **End Date**: 1 day ago (auto-calculated)
- **All Halls**: hall_a, hall_b, hall_c, hall_d
- **Batch Sizes**: Default sizes (extract=5, tag=10, filter=10, validation=10, fixing=10)
- **Filtering**: Disabled by default (use `--filter` to enable)

### Custom Date Range

```bash
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-31
```

### Specific Hall Only

```bash
./scripts/run_pipeline.sh --halls hall_c --start-date 2024-01-01 --end-date 2024-01-31
```

### Verbose Mode

```bash
./scripts/run_pipeline.sh --verbose
```

---

## Step 6: View Results

### Check Output Files

```bash
# Final output
ls -lh data/final_output/

# View faults
cat data/final_output/all_shift_faults.csv

# View manual review items
cat data/final_output/manual_check.csv
```

### Launch Dashboard

```bash
python3 -m streamlit run src/frontend/app.py
```

The dashboard provides:
- **Timeline View**: Faults plotted over time
- **Tag Distribution**: Pie chart of fault categories
- **Hall Comparison**: Bar chart by experimental hall
- **Co-occurrence Heatmap**: Related fault patterns
- **Fault Details**: Clickable table with links

---

## Step 7: Advanced Options

### Adjust Batch Sizes (Performance Tuning)

By default, the pipeline uses batch sizes (extract=5, tag=10, filter=10, validation=10, fixing=10). Adjust to balance speed vs accuracy:

```bash
./scripts/run_pipeline.sh \
  --extract-size 10 \
  --tag-size 20 \
  --filter-size 15 \
  --validation-size 15 \
  --fixing-size 10
```

**Batch size recommendations:**
- **Small (1-5)**: Higher accuracy, slower
- **Medium (5-15)**: Balanced (default)
- **Large (15-30)**: Faster, may reduce accuracy

### Enable Fault Filtering

```bash
./scripts/run_pipeline.sh --filter
```

Removes non-fault entries (routine operations, status updates) before tagging.

---

## Troubleshooting

### "openclaw command not found" (if using OpenClaw mode)

```bash
# Install OpenClaw
npm install -g openclaw

# Or add to PATH
export PATH=$PATH:~/.npm-global/bin
```

**Alternative**: If you don't have OpenClaw installed, use vLLM mode instead:
```bash
# In .env, set:
OPENCLAW_PATH=
VLLM_BASE_URL=http://localhost:8000
VLLM_MODEL_NAME=qwen3-32b
```

### "Configuration validation failed"

Check `.env` file:
- Ensure `JLAB_USERNAME` and `JLAB_PASSWORD` are set
- Verify **either** `OPENCLAW_PATH` **or** `VLLM_BASE_URL`/`VLLM_MODEL_NAME` are configured
- If using OpenClaw mode, ensure `AGENT_NAME` is set and the agent exists
- Check SSH credentials if using tunnel

### "No data loaded"

- Verify date range exists in JLab logbooks
- Check hall names are correct (hall_a, hall_b, hall_c, hall_d)
- Test API access manually:
  ```bash
  curl -u username:password "https://logbooks.jlab.org/api/elog/entries?startdate=2024-01-01&enddate=2024-01-02"
  ```

### "SSH tunnel failed"

```bash
# Test SSH connection manually
ssh your_username@your_host

# Check tunnel ports are available
fuser 8000/tcp
fuser 11435/tcp
```

---

## Next Steps

1. **Read Configuration Guide**: See [CONFIGURATION.md](./CONFIGURATION.md)
2. **Understand Pipeline**: See [ARCHITECTURE.md](./ARCHITECTURE.md)
3. **Performance Tuning**: See [OPERATIONS_PERFORMANCE.md](./OPERATIONS_PERFORMANCE.md)
4. **Dashboard Usage**: See [DASHBOARD.md](./DASHBOARD.md)

---

## Common Commands Cheat Sheet

```bash
# Run for specific date range
./scripts/run_pipeline.sh --start-date 2024-06-01 --end-date 2024-06-30

# Run for Hall C only
./scripts/run_pipeline.sh --halls hall_c --start-date 2024-06-01 --end-date 2024-06-30

# Run with filtering enabled and custom batch sizes
./scripts/run_pipeline.sh --filter --extract-size 10 --tag-size 20 --start-date 2024-06-01 --end-date 2024-06-30

# Run with verbose logging
./scripts/run_pipeline.sh --verbose

# Run without SSH tunnel
./scripts/run_pipeline.sh --no-tunnel

# Adjust batch sizes
./scripts/run_pipeline.sh --extract-size 10 --tag-size 20 --validation-size 15

# Note: Parallelism is handled internally - no workers flag needed

# View help
./scripts/run_pipeline.sh --help
```

---

*For more details, explore the other documentation pages.*
