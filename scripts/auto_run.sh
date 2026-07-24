#!/bin/bash
# CLAW-Agent Auto-Runner
#
# Runs the pipeline once per day at a scheduled time until keyboard interrupt.
# Includes robust error handling, retry logic, and comprehensive logging.
#
# Usage:
#   ./auto_run.sh                           # Run daily at noon
#   ./auto_run.sh --start-time 14:00        # Custom time (HH:MM 24-hour)
#   ./auto_run.sh --agent NAME              # Pass agent name to pipeline
#   ./auto_run.sh --max-retries 3           # Max retries on failure (default: 3)
#   ./auto_run.sh --log-file /path/to/log   # Custom log file path
#
# Press Ctrl+C to stop the scheduler.

# Don't exit on command failure - we handle errors explicitly
# set -e  # REMOVED for robustness

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Project root is the parent of scripts folder
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root
cd "$PROJECT_ROOT"

# Default schedule: noon (12:00 PM)
SCHEDULE_TIME="12:00"

# Retry configuration
MAX_RETRIES=3

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --start-time)
            SCHEDULE_TIME="$2"
            shift 2
            ;;
        --agent)
            AGENT="--agent $2"
            shift 2
            ;;
        --max-retries)
            MAX_RETRIES="$2"
            shift 2
            ;;

        --help)
            echo "Usage: ./auto_run.sh [OPTIONS]"
            echo ""
            echo "Runs the CLAW-Agent pipeline once per day at a scheduled time."
            echo ""
            echo "Options:"
            echo "  --start-time HH:MM    Schedule time in 24-hour format (default: 12:00)"
            echo "  --agent NAME          Pass agent name to pipeline"
            echo "  --max-retries N       Max retries on failure (default: 3)"

            echo ""
            echo "Examples:"
            echo "  ./auto_run.sh                         # Run daily at noon"
            echo "  ./auto_run.sh --start-time 14:00      # Run daily at 2 PM"
            echo "  ./auto_run.sh --agent my-agent        # Run with specific agent"
            echo "  ./auto_run.sh --max-retries 5         # Retry up to 5 times on failure"
            echo ""
            echo "Press Ctrl+C to stop the scheduler."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to calculate dates (2 days ago to 1 day ago)
get_start_date() {
    date -d "2 days ago" +%Y-%m-%d
}

get_end_date() {
    date -d "1 day ago" +%Y-%m-%d
}

# Function to wait until scheduled time
wait_until_scheduled_time() {
    # Parse schedule time, stripping leading zeros to avoid octal interpretation
    local schedule_hour=$((10#$(echo "$SCHEDULE_TIME" | cut -d: -f1)))
    local schedule_minute=$((10#$(echo "$SCHEDULE_TIME" | cut -d: -f2)))
    
    while true; do
        # Get current time, also stripping leading zeros
        local current_hour=$((10#$(date +%H)))
        local current_minute=$((10#$(date +%M)))
        
        # Check if we've reached the scheduled time
        if [[ "$current_hour" -eq "$schedule_hour" && "$current_minute" -lt "$((schedule_minute + 1))" ]]; then
            # Wait until the exact minute starts
            while [[ $((10#$(date +%M))) -ne "$schedule_minute" ]]; do
                sleep 1
            done
            return 0
        fi
        
        # Not yet time, wait a bit and check again
        sleep 60
    done
}

# Logging function (console only)
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local log_line="[$timestamp] [$level] $message"
    
    # Print to console only
    echo "$log_line"
}

# Function to run the pipeline with retry logic
run_pipeline() {
    local start_date=$(get_start_date)
    local end_date=$(get_end_date)
    local attempt=0
    local success=false
    
    log "INFO" "=========================================="
    log "INFO" "Scheduled Pipeline Run - Date Range: $start_date to $end_date"
    log "INFO" "=========================================="
    
    # Build the pipeline command
    local CMD="bash $SCRIPT_DIR/run_pipeline.sh"
    CMD="$CMD --start-date $start_date --end-date $end_date"
    
    # Add agent if specified
    [ -n "$AGENT" ] && CMD="$CMD $AGENT"
    
    log "INFO" "Pipeline command: $CMD"
    log "INFO" "Max retries: $MAX_RETRIES"
    
    # Retry loop
    while [[ $attempt -lt $MAX_RETRIES ]]; do
        attempt=$((attempt + 1))
        log "INFO" "Attempt $attempt/$MAX_RETRIES"
        
        # Run the pipeline and capture output
        local output
        local exit_code
        
        # Run and capture both stdout and stderr
        output=$(eval $CMD 2>&1)
        exit_code=$?
        
        # Log the output (truncate if too long)
        if [[ ${#output} -gt 2000 ]]; then
            log "INFO" "Pipeline output (truncated): ${output:0:2000}..."
        else
            log "INFO" "Pipeline output: $output"
        fi
        
        if [[ $exit_code -eq 0 ]]; then
            success=true
            log "INFO" "Pipeline completed successfully on attempt $attempt!"
            break
        else
            log "ERROR" "Pipeline failed with exit code $exit_code on attempt $attempt"
            
            # If not the last attempt, wait before retrying
            if [[ $attempt -lt $MAX_RETRIES ]]; then
                local wait_time=$((60 * (attempt * attempt)))  # Exponential backoff: 60s, 240s, 540s...
                log "WARN" "Waiting ${wait_time}s before retry (attempt $attempt/$MAX_RETRIES)..."
                sleep $wait_time
            fi
        fi
    done
    
    if [[ "$success" == "true" ]]; then
        log "INFO" "=========================================="
        log "INFO" "Pipeline run successful!"
        log "INFO" "=========================================="
        return 0
    else
        log "ERROR" "=========================================="
        log "ERROR" "Pipeline failed after $MAX_RETRIES attempts!"
        log "ERROR" "=========================================="
        return 1
    fi
}

# Setup shutdown handler with logging
cleanup() {
    log "WARN" "=========================================="
    log "WARN" "Shutdown requested. Stopping scheduler..."
    log "WARN" "=========================================="
    exit 0
}

# Trap multiple signals for robust shutdown handling
trap cleanup SIGINT SIGTERM SIGHUP SIGQUIT

# Main loop
log "INFO" "=========================================="
log "INFO" "CLAW-Agent Auto-Runner Started"
log "INFO" "=========================================="
log "INFO" "Configuration:"
log "INFO" "  Schedule: Daily at $SCHEDULE_TIME"
log "INFO" "  Agent:    ${AGENT:-default}"
log "INFO" "  Max Retries: $MAX_RETRIES"

log "INFO" ""
log "INFO" "Press Ctrl+C to stop."
log "INFO" "Waiting for scheduled time..."
log "INFO" "=========================================="

while true; do
    # Check for shutdown before waiting
    if [[ -f "$PROJECT_ROOT/.stop_scheduler" ]]; then
        log "WARN" "Stop file detected. Stopping scheduler..."
        cleanup
    fi
    
    # Wait until scheduled time
    wait_until_scheduled_time
    
    # Run the pipeline (errors won't stop the scheduler)
    run_pipeline
    pipeline_status=$?
    
    if [[ $pipeline_status -eq 0 ]]; then
        log "INFO" "Pipeline succeeded. Waiting until next scheduled run at $SCHEDULE_TIME tomorrow..."
    else
        log "WARN" "Pipeline failed. Waiting until next scheduled run at $SCHEDULE_TIME tomorrow..."
    fi
    
    # Wait until next day's scheduled time (24 hours from now)
    # Check for stop file periodically during the wait
    wait_remaining=86400  # 24 hours in seconds
    while [[ $wait_remaining -gt 0 ]]; do
        # Check for stop file every 30 seconds
        if [[ -f "$PROJECT_ROOT/.stop_scheduler" ]]; then
            log "WARN" "Stop file detected. Stopping scheduler..."
            cleanup
        fi
        sleep 30
        wait_remaining=$((wait_remaining - 30))
    done
done