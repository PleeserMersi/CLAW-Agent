#!/bin/bash
# outside_cron.sh - Create a daily cron job to run the CLAW-Agent pipeline
#
# Usage:
#   ./outside_cron.sh HH:MM    # Set cron to run daily at specified time (24-hour format)
#   ./outside_cron.sh 02:00    # Example: Run daily at 2:00 AM
#   ./outside_cron.sh 18:30    # Example: Run daily at 6:30 PM
#
# If no argument is provided, shows current cron status and usage.

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Project root is the parent of scripts folder
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Path to run_pipeline.sh
PIPELINE_SCRIPT="$SCRIPT_DIR/run_pipeline.sh"

# Cron job name identifier
CRON_JOB_NAME="CLAW-Agent Pipeline"

# Function to display usage
show_usage() {
    echo "Usage: $0 HH:MM"
    echo ""
    echo "Creates a daily cron job to run the CLAW-Agent pipeline at the specified time."
    echo ""
    echo "Arguments:"
    echo "  HH:MM    Time to run daily (24-hour format, e.g., 02:00 or 18:30)"
    echo ""
    echo "Examples:"
    echo "  $0 02:00    # Run daily at 2:00 AM"
    echo "  $0 18:30    # Run daily at 6:30 PM"
    echo ""
    echo "Current cron status:"
    check_cron_status
    exit 0
}

# Function to check current cron status
check_cron_status() {
    if crontab -l 2>/dev/null | grep -q "$PIPELINE_SCRIPT"; then
        echo "  ✓ Cron job is ACTIVE"
        echo "  Current schedule:"
        crontab -l 2>/dev/null | grep "$PIPELINE_SCRIPT" | sed 's/^/    /'
    else
        echo "  ✗ No cron job found for CLAW-Agent pipeline"
    fi
}

# Function to create/update cron job
create_cron_job() {
    local time_spec="$1"
    
    # Validate time format (HH:MM)
    if ! [[ "$time_spec" =~ ^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$ ]]; then
        echo "Error: Invalid time format '$time_spec'"
        echo "Please use HH:MM format (24-hour), e.g., 02:00 or 18:30"
        exit 1
    fi
    
    # Extract hour and minute
    local hour=$(echo "$time_spec" | cut -d: -f1 | sed 's/^0//')
    local minute=$(echo "$time_spec" | cut -d: -f2 | sed 's/^0//')
    
    # Handle empty values (e.g., "0:00" -> "0 0")
    [ -z "$hour" ] && hour=0
    [ -z "$minute" ] && minute=0
    
    # Build the cron entry
    # Format: minute hour * * * command
    local cron_entry="$minute $hour * * * cd $PROJECT_ROOT && $PIPELINE_SCRIPT >> $PROJECT_ROOT/cron_pipeline.log 2>&1"
    
    # Get existing crontab
    local existing_crontab
    existing_crontab=$(crontab -l 2>/dev/null || echo "")
    
    # Remove any existing CLAW-Agent cron jobs
    local new_crontab
    if [ -n "$existing_crontab" ]; then
        new_crontab=$(echo "$existing_crontab" | grep -v "$PIPELINE_SCRIPT" || true)
    else
        new_crontab=""
    fi
    
    # Add the new cron job
    if [ -n "$new_crontab" ]; then
        new_crontab="$new_crontab
$cron_entry"
    else
        new_crontab="$cron_entry"
    fi
    
    # Install the new crontab
    echo "$new_crontab" | crontab -
    
    echo "✓ Cron job created successfully!"
    echo ""
    echo "Schedule: Daily at $time_spec"
    echo "Script: $PIPELINE_SCRIPT"
    echo "Log file: $PROJECT_ROOT/cron_pipeline.log"
    echo ""
    echo "Current crontab:"
    crontab -l | grep -A0 -B0 "$PIPELINE_SCRIPT" | sed 's/^/  /'
}

# Function to remove cron job
remove_cron_job() {
    local existing_crontab
    existing_crontab=$(crontab -l 2>/dev/null || echo "")
    
    if [ -z "$existing_crontab" ]; then
        echo "No crontab found."
        exit 0
    fi
    
    # Remove CLAW-Agent cron jobs
    local new_crontab
    new_crontab=$(echo "$existing_crontab" | grep -v "$PIPELINE_SCRIPT" || true)
    
    if [ -z "$new_crontab" ]; then
        crontab -r 2>/dev/null || true
        echo "✓ Cron job removed. Crontab is now empty."
    else
        echo "$new_crontab" | crontab -
        echo "✓ Cron job removed successfully."
    fi
}

# Main logic
if [ $# -eq 0 ]; then
    show_usage
elif [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    show_usage
elif [ "$1" == "--remove" ] || [ "$1" == "-r" ]; then
    remove_cron_job
else
    create_cron_job "$1"
fi