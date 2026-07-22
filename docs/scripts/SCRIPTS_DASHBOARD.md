# Dashboard Manager

Reference for `scripts/manage_dashboard.sh`.

---

## Overview

**Dashboard deployment script** that manages the Streamlit dashboard on a remote server via SSH OR runs it locally. Automatically detects configuration and chooses the appropriate mode.

**Location**: `scripts/manage_dashboard.sh`

**Key Features**:
- **Remote mode**: Deploys dashboard to remote server via SSH
- **Local mode**: Runs dashboard on local machine (if SSH credentials not set)
- Syncs data files to remote server (when in remote mode)
- Manages dashboard lifecycle (start/stop/status/sync)
- Automatically detects mode from `.env` configuration
- Access via SSH tunnel (remote) or direct access (local)

---

## Configuration

### Configuration (`.env` file)

The script reads these from `.env` file:

```bash
# Remote server SSH credentials
DASHBOARD_SSH_USERNAME=your_username
DASHBOARD_SSH_HOST=your_server_ip
DASHBOARD_SSH_PORT=22              # Optional, defaults to 22
DASHBOARD_REMOTE_PORT=3335         # Optional, defaults to 3335
```

**Mode Detection**:
- **Remote mode**: If `DASHBOARD_SSH_USERNAME` AND `DASHBOARD_SSH_HOST` are set
- **Local mode**: If either is missing/empty (dashboard runs locally)

**Note**: In local mode, no SSH operations occur - the dashboard runs directly on your machine.

---

## Usage

```bash
./scripts/manage_dashboard.sh [OPTIONS]
```

---

## Options

| Option | Description |
|--------|-------------|
| `--start` | Deploy and start dashboard on remote server |
| `--stop` | Stop dashboard on remote server |
| `--status` | Check dashboard status and file presence |
| `--sync` | Sync data files and restart dashboard |
| `--cleanup` | Remove all CLAW-Agent files from server |
| `--help` | Show help message |

---

## Commands

### `--start` - Deploy and Start

Deploys the dashboard to the remote server and starts it:

```bash
./scripts/manage_dashboard.sh --start
```

**What happens **(Remote mode)
1. Creates remote directory structure: `/home/<user>/CLAW-Agent-Dashboard/src/frontend/`
2. Copies `app.py` to remote server
3. Syncs CSV files from `data/final_output/`
4. Starts dashboard on remote port (default: 3335)
5. Uses `setsid` to detach from SSH session

**What happens **(Local mode)
- Skips deployment (files already local)
- Starts dashboard directly on your machine

**Output**:
```
==========================================
CLAW-Agent Dashboard Manager
==========================================

Step 1: Deploying dashboard files...
Creating directory structure: /home/blankenship/CLAW-Agent-Dashboard/
Copying app.py to /home/blankenship/CLAW-Agent-Dashboard/src/frontend/...
Deployment complete!

Step 2: Syncing data files...
Data sync complete!
Files synced to: blankenship@137.155.253.88:/home/blankenship/CLAW-Agent-Dashboard/data/final_output/

Step 3: Starting dashboard on remote server...
Waiting for dashboard to start...
Dashboard started successfully on port 3335.

==========================================
To view the dashboard, run on your local or remote machine:
  ssh -L 3335:localhost:3335 blankenship@137.155.253.88
Then open: http://localhost:3335
==========================================
```

### `--stop` - Stop Dashboard

Stops the running dashboard on the remote server:

```bash
./scripts/manage_dashboard.sh --stop
```

**What happens**:
1. Checks if dashboard is running on remote port
2. Sends `pkill` to stop streamlit process
3. If still running, uses `fuser -k` to force kill
4. Verifies process is stopped

**Output**:
```
==========================================
Stopping CLAW-Agent Dashboard
==========================================
Stopping process on port 3335...
Dashboard stopped successfully.
==========================================
```

### `--status` - Check Status

Checks dashboard deployment and running status:

```bash
./scripts/manage_dashboard.sh --status
```

**What it checks**:
- `app.py` presence on remote server
- CSV files in `data/final_output/`
- Dashboard running status (port binding)
- Process PID if running

**Output**:
```
==========================================
CLAW-Agent Dashboard Status
==========================================
Dashboard files:
  src/frontend/app.py: PRESENT

Data files:
  data/final_output/ CSV files: 2
    /home/blankenship/CLAW-Agent/data/final_output/all_shift_faults.csv: 15K
    /home/blankenship/CLAW-Agent/data/final_output/manual_check.csv: 1.2K

Dashboard status:
  Status: RUNNING (PID: 12345)
  Port: 3335
  Location: /home/blankenship/CLAW-Agent/src/frontend/app.py
  Data: /home/blankenship/CLAW-Agent/data/final_output/
  SSH Command: ssh -L 3335:localhost:3335 blankenship@137.155.253.88
  URL: http://localhost:3335
==========================================
```

### `--sync` - Sync and Restart

Syncs data files and restarts the dashboard:

```bash
./scripts/manage_dashboard.sh --sync
```

**What happens**:
1. Syncs CSV files from local `data/final_output/` to remote (or confirms local in local mode)
2. **Stops** existing dashboard
3. **Starts** fresh dashboard with new data

**Use case**: Update dashboard data after running the pipeline without full redeployment.

**Note**: This always restarts the dashboard to ensure data is reloaded.

### `--cleanup` - Remove from Server

**Destructive**: Removes entire dashboard directory from remote server:

```bash
./scripts/manage_dashboard.sh --cleanup
```

**What happens **(Remote mode)
1. Stops dashboard if running
2. Force kills process if needed
3. Removes entire `/home/<user>/CLAW-Agent-Dashboard/` directory
4. Verifies removal

**What happens **(Local mode)
- Only stops the local dashboard
- Does **not** delete local files (manual cleanup required)

**Confirmation required**: Asks "Are you sure you want to continue? (yes/no)?" before remote deletion

**Output**:
```
==========================================
Cleaning up dashboard files from server
==========================================
WARNING: This will delete the entire /home/blankenship/CLAW-Agent-Dashboard folder on the server.
This includes all files and subdirectories.

Are you sure you want to continue? (yes/no): yes
Dashboard is running. Stopping it first...
Dashboard stopped.
Removing entire /home/blankenship/CLAW-Agent-Dashboard folder from server...
CLAW-Agent-Dashboard folder removed.

Verification:
  /home/blankenship/CLAW-Agent-Dashboard: REMOVED

Cleanup complete!
==========================================
```

---

## Accessing the Dashboard

### SSH Tunnel Setup

After starting with `--start`, create SSH tunnel on your local machine:

```bash
ssh -L 3335:localhost:3335 blankenship@137.155.253.88
```

Then open in browser:
```
http://localhost:3335
```

### Direct Server Access

If logged into the server directly:
```
http://localhost:3335
```

---

## Remote Server Details

**Default Configuration**:
- **SSH Port**: 22 (configurable via `DASHBOARD_SSH_PORT`)
- **Dashboard Port**: 3335 (configurable via `DASHBOARD_REMOTE_PORT`)
- **User**: Configured in `.env` (`DASHBOARD_SSH_USERNAME`)
- **Remote Path**: `/home/<user>/CLAW-Agent-Dashboard/` (note: `-Dashboard` suffix)

**Remote Directory Structure**:
```
/home/<user>/CLAW-Agent-Dashboard/
├── src/frontend/
│   └── app.py           # Dashboard app (deployed here)
└── data/final_output/
    └── *.csv            # Synced data files
```

**Local Mode Paths**:
- App: `src/frontend/app.py` (in project root)
- Data: `data/final_output/*.csv`

---

## Error Handling

### Missing `.env` File
```
ERROR: .env file not found at /home/user/Desktop/CLAW-Agent/.env
```

### Missing Required Variables
```
ERROR: DASHBOARD_SSH_USERNAME and DASHBOARD_SSH_HOST must be set in .env file
```

### Local Files Missing
```
ERROR: Local app.py not found at /home/user/Desktop/CLAW-Agent/src/frontend/app.py
ERROR: Data directory not found at /home/user/Desktop/CLAW-Agent/data/final_output
```

### Dashboard Already Running
```
Dashboard is already running on port 3335. Skipping start.

### Local Mode Active
```
Note: DASHBOARD_SSH_USERNAME or DASHBOARD_SSH_HOST not set. Running dashboard locally.
```
```

### Failed to Stop
```
WARNING: Could not stop dashboard on port 3335.

### No CSV Files to Sync
```
WARNING: No CSV files found in /path/to/data/final_output
```
```

---

## Troubleshooting

### Dashboard Won't Start

1. **Check SSH connectivity**:
   ```bash
   ssh blankenship@137.155.253.88
   ```

2. **Verify port is available**:
   ```bash
   ssh blankenship@137.155.253.88 "ss -tlnp | grep 3335"
   ```

3. **Check remote logs**:
   ```bash
   ssh blankenship@137.155.253.88 "cat /tmp/streamlit_3335.log"
   ```

4. **Ensure streamlit is installed on server**:
   ```bash
   ssh blankenship@137.155.253.88 "which streamlit"
   ```

### Data Not Updating

1. **Manually sync**:
   ```bash
   ./scripts/manage_dashboard.sh --sync
   ```

2. **Verify CSV files exist locally**:
   ```bash
   ls -la data/final_output/
   ```

3. **Check remote data **(remote mode)
   ```bash
   ssh user@host "ls -la /home/user/CLAW-Agent-Dashboard/data/final_output/"
   ```

4. **Check local data **(local mode)
   ```bash
   ls -la data/final_output/
   ```

### Cannot Access Dashboard

**Remote mode**:
1. **Verify SSH tunnel is active**:
   ```bash
   netstat -tlnp | grep 3335
   ```

2. **Recreate tunnel**:
   ```bash
   # Kill existing tunnel
   kill $(lsof -ti:3335)
   
   # Start new tunnel
   ssh -L 3335:localhost:3335 user@host
   ```

3. **Check dashboard is running on server**:
   ```bash
   ./scripts/manage_dashboard.sh --status
   ```

**Local mode**:
1. **Check if dashboard is running locally**:
   ```bash
   ss -tlnp | grep 3335
   ```

2. **Direct access**:
   - No SSH tunnel needed
   - Open `http://localhost:3335` directly

---

## Manual Commands (Remote Mode)

If you prefer manual SSH commands:

```bash
# Deploy app.py
scp src/frontend/app.py user@host:/home/user/CLAW-Agent-Dashboard/src/frontend/

# Sync data
scp data/final_output/*.csv user@host:/home/user/CLAW-Agent-Dashboard/data/final_output/

# Start dashboard (note: CLAW-Agent-Dashboard path)
ssh user@host "cd /home/user/CLAW-Agent-Dashboard && setsid streamlit run src/frontend/app.py --server.port 3335 --server.address 0.0.0.0 --server.headless true > /tmp/streamlit_3335.log 2>&1 &"

# Check status
ssh user@host "ss -tlnp | grep 3335"

# Stop dashboard
ssh user@host "pkill -f 'streamlit.*:3335'"
```

**Note**: The remote path is `/home/user/CLAW-Agent-Dashboard` (with `-Dashboard` suffix), not `CLAW-Agent`.

---

## Quick Reference

```bash
# Deploy and start (remote or local)
./scripts/manage_dashboard.sh --start

# Stop dashboard
./scripts/manage_dashboard.sh --stop

# Check status
./scripts/manage_dashboard.sh --status

# Sync data and restart
./scripts/manage_dashboard.sh --sync

# Remove from server (remote only)
./scripts/manage_dashboard.sh --cleanup

# View help
./scripts/manage_dashboard.sh --help
```

## Related Documentation

- [Dashboard Guide](../getting-started/DASHBOARD.md) - Dashboard usage and features
- [Configuration](../config/CONFIGURATION.md) - Environment setup
- [Pipeline Operations](../pipeline/OPERATIONS_PIPELINE.md) - Pipeline operations

---

*For dashboard usage details, see [DASHBOARD.md](../getting-started/DASHBOARD.md).*