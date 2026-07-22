# Installation Guide

Complete installation and setup instructions for CLAW-Agent.

---

## Prerequisites

### Required Software

- **Python**: 3.8 or higher
- **OpenClaw**: Installed and configured (`openclaw` command available)
- **Git**: For version control (optional)
- **SSH Client**: For remote access (optional)

### Required Accounts

- **JLab Logbook API**: Username and password
- **SSH Access**: (Optional) For remote infrastructure

---

## Step-by-Step Installation

### 1. Clone/Navigate to Project

```bash
cd /home/sec-researchonly/Desktop/CLAW-Agent
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Dependencies installed**:
- pandas>=2.0.0
- numpy>=1.24.0
- requests>=2.31.0
- beautifulsoup4>=4.12.0
- pydantic>=2.0.0
- ollama>=0.1.0
- streamlit>=1.28.0
- plotly>=5.17.0
- chromadb>=0.5.0
- sentence-transformers>=3.0.0
- python-dotenv>=1.0.0
- matplotlib>=3.10.0

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required settings**:
```bash
JLAB_USERNAME=your_username
JLAB_PASSWORD=your_password
AGENT_NAME=fault_analyst
```

**Optional SSH settings**:
```bash
SSH_USERNAME=your_ssh_user
SSH_HOST=your_ssh_host
SSH_TUNNEL_1_LOCAL=8000
SSH_TUNNEL_1_REMOTE=8001
SSH_TUNNEL_2_LOCAL=11435
SSH_TUNNEL_2_REMOTE=11434
```

### 5. Verify OpenClaw Setup

```bash
# Check OpenClaw is available
which openclaw

# Test agent
openclaw agent --agent fault_analyst --message "Hello"
```

### 6. Test Installation

```bash
# Run help to verify
./scripts/run_pipeline.sh --help

# Run a quick test (1 day range)
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-02 --no-tunnel
```

---

## Verification

### Check Dependencies

```bash
python3 -c "import pandas; import numpy; import chromadb; import streamlit; print('All dependencies installed')"
```

### Check Configuration

```bash
python3 -c "from config import validate_config_strict; validate_config_strict()"
```

### Check Directories

```bash
ls -la data/raw/ data/processed/ data/verified/ data/fixed/ data/final_output/
```

---

## Troubleshooting

### "python3: command not found"

**Fix**: Install Python 3.8+

```bash
# Ubuntu/Debian
sudo apt install python3.10 python3-venv python3-pip

# RHEL/CentOS
sudo dnf install python3.10 python3-virtualenv python3-pip
```

### "pip not found"

**Fix**: Install pip

```bash
python3 -m ensurepip --upgrade
```

### "No module named 'pandas'"

**Fix**: Install dependencies

```bash
pip install -r requirements.txt
```

### "openclaw command not found"

**Fix**: Install OpenClaw

```bash
npm install -g openclaw
```

Or add to PATH:
```bash
export PATH=$PATH:~/.npm-global/bin
```

### "Permission denied"

**Fix**: Check file permissions

```bash
chmod +x scripts/run_pipeline.sh
chmod +x scripts/*.sh
```

---

## Post-Installation

### Create Log Directory

```bash
mkdir -p logs
```

### Set Up Automatic Activation

Add to `~/.bashrc`:
```bash
# CLAW-Agent virtual environment
if [ -d /home/sec-researchonly/Desktop/CLAW-Agent/venv ]; then
    alias claw='cd /home/sec-researchonly/Desktop/CLAW-Agent && source venv/bin/activate'
fi
```

Then reload:
```bash
source ~/.bashrc
claw  # Activate and cd into project
```

### Test Full Pipeline

```bash
# Run with small date range
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-02 --verbose

# Check output
ls -lh data/final_output/
cat data/final_output/all_shift_faults.csv
```

---

## Uninstallation

### Remove Virtual Environment

```bash
cd /home/sec-researchonly/Desktop/CLAW-Agent
rm -rf venv
```

### Remove Project

```bash
rm -rf /home/sec-researchonly/Desktop/CLAW-Agent
```

### Clean Dependencies (if installed globally)

```bash
pip uninstall pandas numpy chromadb streamlit plotly
```

---

## Related Documentation

- [Quick Start](./QUICKSTART.md) - Fast setup
- [Configuration](./CONFIGURATION.md) - Environment setup
- [Operations](./OPERATIONS_PIPELINE.md) - Running the pipeline

---

*For quick setup, see [QUICKSTART.md](./QUICKSTART.md).*