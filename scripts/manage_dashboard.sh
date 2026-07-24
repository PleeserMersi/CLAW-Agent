#!/bin/bash
# CLAW-Agent Dashboard Manager
#
# Deploys and manages the Streamlit dashboard on the remote GPU server.
# Maintains the same directory structure as the local project.
#
# Usage:
#   ./manage_dashboard.sh --start     # Deploy and start dashboard on server
#   ./manage_dashboard.sh --stop      # Stop dashboard on server
#   ./manage_dashboard.sh --status    # Check dashboard status
#   ./manage_dashboard.sh --sync      # Only sync data files
#   ./manage_dashboard.sh --help      # Show help
#
# The dashboard runs independently on the server after --start.
# Access via SSH tunnel: ssh -L 3335:localhost:3335 blankenship@137.155.253.88
# Then open: http://localhost:3335

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment variables from .env file
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    # Extract dashboard-specific SSH variables from .env
    DASHBOARD_SSH_USERNAME=$(grep "^DASHBOARD_SSH_USERNAME=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"')
    DASHBOARD_SSH_HOST=$(grep "^DASHBOARD_SSH_HOST=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"')
    DASHBOARD_SSH_PORT=$(grep "^DASHBOARD_SSH_PORT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"')
    DASHBOARD_REMOTE_PORT=$(grep "^DASHBOARD_REMOTE_PORT=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"')
else
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

# SSH options to suppress warnings
SSH_OPTS="-o LogLevel=ERROR"

# Determine if we're running in remote or local mode
REMOTE_MODE=true
if [ -z "$DASHBOARD_SSH_USERNAME" ] || [ -z "$DASHBOARD_SSH_HOST" ]; then
    # Missing SSH credentials - run locally
    REMOTE_MODE=false
    echo "Note: DASHBOARD_SSH_USERNAME or DASHBOARD_SSH_HOST not set. Running dashboard locally."
fi

REMOTE_PORT="${DASHBOARD_REMOTE_PORT:-3335}"

# Remote server configuration (only used if REMOTE_MODE=true)
REMOTE_USER="$DASHBOARD_SSH_USERNAME"
REMOTE_HOST="$DASHBOARD_SSH_HOST"
REMOTE_SSH_PORT="${DASHBOARD_SSH_PORT:-22}"
REMOTE_PROJECT_DIR="/home/$REMOTE_USER/CLAW-Agent-Dashboard"
REMOTE_DIR="$REMOTE_PROJECT_DIR/src/frontend"
REMOTE_DATA_DIR="$REMOTE_PROJECT_DIR/data/final_output"

# Local configuration
LOCAL_APP="$PROJECT_ROOT/src/frontend/app.py"
LOCAL_DATA_DIR="$PROJECT_ROOT/data/final_output"

# Parse arguments
ACTION=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --start)
            ACTION="start"
            shift
            ;;
        --stop)
            ACTION="stop"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --sync)
            ACTION="sync"
            shift
            ;;
        --cleanup)
            ACTION="cleanup"
            shift
            ;;
        --help)
            echo "CLAW-Agent Dashboard Manager"
            echo ""
            echo "Usage: ./manage_dashboard.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --start     Deploy and start dashboard (remote or local)"
            echo "  --stop      Stop dashboard (remote or local)"
            echo "  --status    Check dashboard status"
            echo "  --sync      Only sync data files (no restart)"
            echo "  --cleanup   Remove dashboard files from server (stops dashboard first)"
            echo "  --help      Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./manage_dashboard.sh --start    # Deploy and start"
            echo "  ./manage_dashboard.sh --stop     # Stop dashboard"
            echo "  ./manage_dashboard.sh --status   # Check status"
            echo "  ./manage_dashboard.sh --sync     # Update data only"
            echo ""
            if [ "$REMOTE_MODE" = true ]; then
                echo "Remote mode: Dashboard runs on server"
                echo "After starting, access via SSH tunnel:"
                echo "  ssh -L $REMOTE_PORT:localhost:$REMOTE_PORT $REMOTE_USER@$REMOTE_HOST"
                echo "  Then open: http://localhost:$REMOTE_PORT"
            else
                echo "Local mode: Dashboard runs on this machine"
                echo "After starting, open directly:"
                echo "  http://localhost:$REMOTE_PORT"
            fi
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

if [ -z "$ACTION" ]; then
    echo "ERROR: No action specified. Use --help for usage information."
    exit 1
fi

# Check if local app file exists
if [ ! -f "$LOCAL_APP" ]; then
    echo "ERROR: Local app.py not found at $LOCAL_APP"
    exit 1
fi

# Check if data directory exists
if [ ! -d "$LOCAL_DATA_DIR" ]; then
    echo "ERROR: Data directory not found at $LOCAL_DATA_DIR"
    exit 1
fi

# Function: Deploy app and dependencies to server
deploy_app() {
    if [ "$REMOTE_MODE" = true ]; then
        echo "Deploying dashboard to remote server..."
        
        # Create remote directory structure
        echo "Creating directory structure: $REMOTE_PROJECT_DIR/"
        ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_DIR"
        ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "mkdir -p $REMOTE_DATA_DIR"
        
        # Copy app.py to correct location
        echo "Copying app.py to $REMOTE_DIR/..."
        scp -q "$LOCAL_APP" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/app.py"
        
        echo "Deployment complete!"
    else
        echo "Local mode: No deployment needed. Using local files."
    fi
}

# Function: Sync data files
sync_data() {
    if [ "$REMOTE_MODE" = true ]; then
        echo "Syncing data files to remote server..."
        
        # Sync all CSV files from final_output
        scp -q "$LOCAL_DATA_DIR"/*.csv "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DATA_DIR/" 2>/dev/null || {
            echo "WARNING: No CSV files found in $LOCAL_DATA_DIR"
        }
        
        echo "Data sync complete!"
        echo "Files synced to: $REMOTE_USER@$REMOTE_HOST:$REMOTE_DATA_DIR/"
    else
        echo "Local mode: Data files already local at $LOCAL_DATA_DIR"
    fi
}

# Function: Start dashboard
start_dashboard() {
    echo "=========================================="
    echo "CLAW-Agent Dashboard Manager"
    echo "=========================================="
    echo ""
    
    if [ "$REMOTE_MODE" = true ]; then
        # Deploy app if needed
        echo "Step 1: Deploying dashboard files..."
        deploy_app
        
        # Sync data
        echo ""
        echo "Step 2: Syncing data files..."
        scp -q "$LOCAL_DATA_DIR"/*.csv "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DATA_DIR/" 2>/dev/null || {
            echo "WARNING: No CSV files found in $LOCAL_DATA_DIR"
        }
        
        # Start dashboard
        echo ""
        echo "Step 3: Starting dashboard on remote server..."
        
        # Check if dashboard is already running
        if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
            echo "Dashboard is already running on port $REMOTE_PORT. Skipping start."
        else
            # Change to project root (not src/frontend) so relative paths work
            # Use setsid to fully detach from SSH session
            ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "setsid bash -c 'cd $REMOTE_PROJECT_DIR && streamlit run src/frontend/app.py --server.port $REMOTE_PORT --server.address 0.0.0.0 --server.headless true > /tmp/streamlit_$REMOTE_PORT.log 2>&1' >/dev/null 2>&1 &"
            
            # Wait for dashboard to start
            echo "Waiting for dashboard to start..."
            sleep 5
            
            # Verify it started
            if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
                echo "Dashboard started successfully on port $REMOTE_PORT."
            else
                echo "WARNING: Dashboard may not have started correctly."
            fi
        fi
        
        echo ""
        echo "=========================================="
        echo "To view the dashboard, run on your local or remote machine:"
        echo "  ssh -L $REMOTE_PORT:localhost:$REMOTE_PORT $REMOTE_USER@$REMOTE_HOST"
        echo "Then open: http://localhost:$REMOTE_PORT"
        echo "=========================================="
    else
        # Local mode - run dashboard directly
        echo "Step 1: Local mode - using local files"
        
        # Check if data files exist
        if [ ! -d "$LOCAL_DATA_DIR" ] || [ -z "$(ls -A $LOCAL_DATA_DIR/*.csv 2>/dev/null)" ]; then
            echo "WARNING: No CSV files found in $LOCAL_DATA_DIR"
        fi
        
        # Start dashboard locally
        echo ""
        echo "Step 2: Starting dashboard locally on port $REMOTE_PORT..."
        
        # Check if dashboard is already running locally
        if ss -tlnp 2>/dev/null | grep -q ":$REMOTE_PORT "; then
            echo "Dashboard is already running on port $REMOTE_PORT. Skipping start."
        else
            # Change to project root so relative paths work
            cd "$PROJECT_ROOT"
            
            # Activate virtual environment if it exists
            VENV_DIR="$PROJECT_ROOT/venv"
            if [ -f "$VENV_DIR/bin/activate" ]; then
                echo "Activating virtual environment..."
                source "$VENV_DIR/bin/activate"
            fi
            
            nohup streamlit run src/frontend/app.py --server.port $REMOTE_PORT --server.address 0.0.0.0 --server.headless true > /tmp/streamlit_$REMOTE_PORT.log 2>&1 &
            DASHBOARD_PID=$!
            
            # Wait for dashboard to start
            echo "Waiting for dashboard to start..."
            sleep 5
            
            # Verify it started
            if ss -tlnp 2>/dev/null | grep -q ":$REMOTE_PORT "; then
                echo "Dashboard started successfully on port $REMOTE_PORT (PID: $DASHBOARD_PID)."
            else
                echo "WARNING: Dashboard may not have started correctly. Check /tmp/streamlit_$REMOTE_PORT.log"
            fi
        fi
        
        echo ""
        echo "=========================================="
        echo "Dashboard is running locally."
        echo "Open: http://localhost:$REMOTE_PORT"
        echo "=========================================="
    fi
}

# Function: Stop dashboard
stop_dashboard() {
    echo "=========================================="
    echo "Stopping CLAW-Agent Dashboard"
    echo "=========================================="
    
    if [ "$REMOTE_MODE" = true ]; then
        # First check if it's running
        if ! ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
            echo "Dashboard is not running on port $REMOTE_PORT."
            echo "=========================================="
            return 0
        fi
        
        echo "Stopping process on port $REMOTE_PORT..."
        
        # Try pkill first
        ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "pkill -f 'streamlit.*:$REMOTE_PORT'" 2>/dev/null || true
        
        # Wait a moment
        sleep 2
        
        # Check if still running
        if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
            echo "Process still running, forcing kill..."
            ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "fuser -k $REMOTE_PORT/tcp" 2>/dev/null || true
            sleep 2
        fi
        
        # Final check
        if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
            echo "WARNING: Could not stop dashboard on port $REMOTE_PORT."
            echo "=========================================="
            return 1
        fi
        
        echo "Dashboard stopped successfully."
    else
        # Local mode
        if ! ss -tlnp 2>/dev/null | grep -q ":$REMOTE_PORT "; then
            echo "Dashboard is not running on port $REMOTE_PORT."
            echo "=========================================="
            return 0
        fi
        
        echo "Stopping local process on port $REMOTE_PORT..."
        
        # Try pkill first
        pkill -f "streamlit.*:$REMOTE_PORT" 2>/dev/null || true
        
        # Wait a moment
        sleep 2
        
        # Check if still running
        if ss -tlnp 2>/dev/null | grep -q ":$REMOTE_PORT "; then
            echo "Process still running, forcing kill..."
            fuser -k $REMOTE_PORT/tcp 2>/dev/null || true
            sleep 2
        fi
        
        # Final check
        if ss -tlnp 2>/dev/null | grep -q ":$REMOTE_PORT "; then
            echo "WARNING: Could not stop dashboard on port $REMOTE_PORT."
            echo "=========================================="
            return 1
        fi
        
        echo "Dashboard stopped successfully."
    fi
    echo "=========================================="
}

# Function: Check status
check_status() {
    echo "=========================================="
    echo "CLAW-Agent Dashboard Status"
    echo "=========================================="
    
    if [ "$REMOTE_MODE" = true ]; then
        # Check if app exists on server
        echo "Dashboard files:"
        if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "test -f $REMOTE_DIR/app.py" 2>/dev/null; then
            echo "  src/frontend/app.py: PRESENT"
        else
            echo "  src/frontend/app.py: NOT FOUND (run --start first)"
        fi
        
        # Check data files
        echo ""
        echo "Data files:"
        DATA_COUNT=$(ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ls -1 $REMOTE_DATA_DIR/*.csv 2>/dev/null | wc -l")
        echo "  data/final_output/ CSV files: $DATA_COUNT"
        
        if [ "$DATA_COUNT" -gt 0 ]; then
            ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ls -lh $REMOTE_DATA_DIR/*.csv 2>/dev/null | awk '{print \"    \" $9 \": \" $5}'"
        fi
        
        # Check if running
        echo ""
        echo "Dashboard status:"
        if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
            PID=$(ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep ':$REMOTE_PORT ' | grep -oP 'pid=\K[0-9]+' | head -1")
            echo "  Status: RUNNING (PID: $PID)"
            echo "  Port: $REMOTE_PORT"
            echo "  Location: $REMOTE_DIR/app.py"
            echo "  Data: $REMOTE_DATA_DIR/"
            echo "  SSH Command: ssh -L $REMOTE_PORT:localhost:$REMOTE_PORT $REMOTE_USER@$REMOTE_HOST"
            echo "  URL: http://localhost:$REMOTE_PORT"
        else
            echo "  Status: NOT RUNNING"
            echo "  Run: ./manage_dashboard.sh --start"
        fi
    else
        # Local mode
        echo "Local mode: Running on this machine"
        echo ""
        echo "Dashboard files:"
        if [ -f "$LOCAL_APP" ]; then
            echo "  src/frontend/app.py: PRESENT"
        else
            echo "  src/frontend/app.py: NOT FOUND"
        fi
        
        # Check data files
        echo ""
        echo "Data files:"
        if [ -d "$LOCAL_DATA_DIR" ]; then
            DATA_COUNT=$(ls -1 "$LOCAL_DATA_DIR"/*.csv 2>/dev/null | wc -l)
            echo "  data/final_output/ CSV files: $DATA_COUNT"
            if [ "$DATA_COUNT" -gt 0 ]; then
                ls -lh "$LOCAL_DATA_DIR"/*.csv 2>/dev/null | awk '{print "    " $9 ": " $5}'
            fi
        else
            echo "  data/final_output/: NOT FOUND"
        fi
        
        # Check if running
        echo ""
        echo "Dashboard status:"
        if ss -tlnp 2>/dev/null | grep -q ":$REMOTE_PORT "; then
            PID=$(ss -tlnp 2>/dev/null | grep ":$REMOTE_PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
            echo "  Status: RUNNING (PID: $PID)"
            echo "  Port: $REMOTE_PORT"
            echo "  Location: $LOCAL_APP"
            echo "  Data: $LOCAL_DATA_DIR/"
            echo "  URL: http://localhost:$REMOTE_PORT"
        else
            echo "  Status: NOT RUNNING"
            echo "  Run: ./manage_dashboard.sh --start"
        fi
    fi
    
    echo "=========================================="
}

# Main action
case "$ACTION" in
    start)
        start_dashboard
        ;;
    stop)
        stop_dashboard
        ;;
    status)
        check_status
        ;;
    sync)
        echo "=========================================="
        echo "Syncing data files and restarting dashboard"
        echo "=========================================="
        sync_data
        echo ""
        echo "Restarting dashboard with updated data..."
        # Stop existing dashboard first to ensure data reload
        stop_dashboard
        echo ""
        # Start fresh
        start_dashboard
        ;;
    cleanup)
        echo "=========================================="
        echo "Cleaning up dashboard files"
        echo "=========================================="
        
        if [ "$REMOTE_MODE" = true ]; then
            # Confirm deletion of entire CLAW-Agent folder
            echo "WARNING: This will delete the entire $REMOTE_PROJECT_DIR folder on the server."
            echo "This includes all files and subdirectories."
            echo ""
            read -p "Are you sure you want to continue? (yes/no): " confirm
            if [ "$confirm" != "yes" ]; then
                echo "Cleanup cancelled."
                exit 0
            fi
            
            # Stop dashboard if running
            if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
                echo "Dashboard is running. Stopping it first..."
                ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "pkill -f 'streamlit.*:$REMOTE_PORT'" 2>/dev/null || true
                sleep 2
                
                # Force kill if still running
                if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "ss -tlnp 2>/dev/null | grep -q ':$REMOTE_PORT '"; then
                    echo "Force killing process..."
                    ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "fuser -k $REMOTE_PORT/tcp" 2>/dev/null || true
                    sleep 2
                fi
                echo "Dashboard stopped."
            else
                echo "Dashboard was not running."
            fi
            
            # Remove entire CLAW-Agent folder
            echo "Removing entire $REMOTE_PROJECT_DIR folder from server..."
            ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "rm -rf $REMOTE_PROJECT_DIR"
            echo "CLAW-Agent folder removed."
            
            # Verify cleanup
            echo ""
            echo "Verification:"
            if ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "test -d $REMOTE_PROJECT_DIR" 2>/dev/null; then
                echo "  WARNING: $REMOTE_PROJECT_DIR still exists on server"
            else
                echo "  $REMOTE_PROJECT_DIR: REMOVED"
            fi
        else
            # Local mode - just stop the dashboard
            echo "Local mode: No remote cleanup needed."
            echo "Stopping local dashboard if running..."
            stop_dashboard
            echo ""
            echo "To remove local files, manually delete:"
            echo "  $LOCAL_APP"
            echo "  $LOCAL_DATA_DIR/*.csv"
        fi
        
        echo ""
        echo "Cleanup complete!"
        echo "=========================================="
        ;;
    *)
        echo "Unknown action: $ACTION"
        exit 1
        ;;
esac