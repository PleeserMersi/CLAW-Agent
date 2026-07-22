#!/bin/bash
# CLAW-Agent Date-Batched Pipeline Runner
#
# Runs the pipeline in one-month increments across the specified date range.
# Each month is processed sequentially, waiting for completion before starting the next.
#
# Usage:
#   ./run_pipeline_date_batched.sh --start-date 2025-05-01 --end-date 2025-07-01
#   ./run_pipeline_date_batched.sh --start-date 2024-01-15 --end-date 2024-03-10 --verbose
#   ./run_pipeline_date_batched.sh --start-date 2024-11-01 --end-date 2025-02-28 --filter
#
# The script will:
#   1. Loop from start_date to end_date in one-month increments
#   2. Run run_pipeline.sh for each month-long batch
#   3. Handle year transitions and varying month lengths correctly
#   4. Pass all other arguments (verbose, filter, etc.) to each run

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Project root is the parent of scripts folder
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root
cd "$PROJECT_ROOT"

# Function to add one month to a date string (YYYY-MM-DD)
add_one_month() {
    local date_str="$1"
    local year="${date_str:0:4}"
    local month="${date_str:5:2}"
    local day="${date_str:8:2}"
    
    # Remove leading zeros for arithmetic
    month=$((10#$month))
    year=$((10#$year))
    day=$((10#$day))
    
    # Increment month
    month=$((month + 1))
    if [ $month -gt 12 ]; then
        month=1
        year=$((year + 1))
    fi
    
    # Format back with leading zeros
    printf "%04d-%02d-%02d" "$year" "$month" "$day"
}

# Function to get the last day of a given month/year
get_last_day_of_month() {
    local year="$1"
    local month="$2"
    
    # Use date command to get last day
    if [ "$month" -eq 12 ]; then
        next_year=$((year + 1))
        next_month=1
    else
        next_year=$year
        next_month=$((month + 1))
    fi
    
    # Get last day of current month by subtracting 1 day from first of next month
    last_day=$(date -d "$next_year-$next_month-01 -1 day" +%d)
    echo "$last_day"
}

# Function to validate date format
validate_date() {
    local date_str="$1"
    if ! date -d "$date_str" >/dev/null 2>&1; then
        echo "Error: Invalid date format: $date_str. Use YYYY-MM-DD."
        exit 1
    fi
}

# Parse arguments
START_DATE=""
END_DATE=""
VERBOSE=""
NO_TUNNEL=""
FILTER=""
AGENT=""
EXTRACT_SIZE=""
TAG_SIZE=""
FILTER_SIZE=""
VALIDATION_SIZE=""
FIXING_SIZE=""
HALLS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --start-date)
            START_DATE="$2"
            shift 2
            ;;
        --end-date)
            END_DATE="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE="--verbose"
            shift
            ;;
        --no-tunnel)
            NO_TUNNEL="--no-tunnel"
            shift
            ;;
        --filter)
            FILTER="--filter"
            shift
            ;;
        --agent)
            AGENT="--agent $2"
            shift 2
            ;;
        --extract-size)
            EXTRACT_SIZE="--extract-size $2"
            shift 2
            ;;
        --tag-size)
            TAG_SIZE="--tag-size $2"
            shift 2
            ;;
        --filter-size)
            FILTER_SIZE="--filter-size $2"
            shift 2
            ;;
        --validation-size)
            VALIDATION_SIZE="--validation-size $2"
            shift 2
            ;;
        --fixing-size)
            FIXING_SIZE="--fixing-size $2"
            shift 2
            ;;
        --halls)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                if [ -z "$HALLS" ]; then
                    HALLS="--halls $1"
                else
                    HALLS="$HALLS $1"
                fi
                shift
            done
            ;;
        --help)
            echo "Usage: ./run_pipeline_date_batched.sh [OPTIONS]"
            echo ""
            echo "Runs the CLAW-Agent fault extraction pipeline in one-month batches."
            echo ""
            echo "Required Options:"
            echo "  --start-date YYYY-MM-DD  Start date (inclusive)"
            echo "  --end-date YYYY-MM-DD    End date (exclusive)"
            echo ""
            echo "Pipeline Options:"
            echo "  --verbose                Enable verbose logging"
            echo "  --no-tunnel              Skip SSH tunnel creation"
            echo "  --filter                 Enable fault filtering step"
            echo "  --agent NAME             Agent for all pipeline stages"
            echo "  --extract-size N         Batch size for extraction (default: 5)"
            echo "  --tag-size N             Batch size for tagging (default: 10)"
            echo "  --filter-size N          Batch size for filtering (default: 10)"
            echo "  --validation-size N      Batch size for verification (default: 10)"
            echo "  --fixing-size N          Batch size for fixing (default: 10)"
            echo "  --halls HALL1 [HALL2...]  Hall(s) to process"
            echo ""
            echo "Examples:"
            echo "  ./run_pipeline_date_batched.sh --start-date 2025-05-01 --end-date 2025-07-01"
            echo "  ./run_pipeline_date_batched.sh --start-date 2024-01-15 --end-date 2024-03-10 --verbose"
            echo "  ./run_pipeline_date_batched.sh --start-date 2024-11-01 --end-date 2025-02-28 --filter --halls hall_a hall_b"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [ -z "$START_DATE" ] || [ -z "$END_DATE" ]; then
    echo "Error: Both --start-date and --end-date are required."
    echo "Usage: ./run_pipeline_date_batched.sh --start-date YYYY-MM-DD --end-date YYYY-MM-DD [OPTIONS]"
    exit 1
fi

# Validate date formats
validate_date "$START_DATE"
validate_date "$END_DATE"

# Check that start_date is before end_date
if [[ "$START_DATE" > "$END_DATE" ]]; then
    echo "Error: Start date ($START_DATE) must be before end date ($END_DATE)."
    exit 1
fi

# Set default batch sizes if not provided
[ -z "$EXTRACT_SIZE" ] && EXTRACT_SIZE="--extract-size 5"
[ -z "$TAG_SIZE" ] && TAG_SIZE="--tag-size 10"
[ -z "$FILTER_SIZE" ] && FILTER_SIZE="--filter-size 10"
[ -z "$VALIDATION_SIZE" ] && VALIDATION_SIZE="--validation-size 10"
[ -z "$FIXING_SIZE" ] && FIXING_SIZE="--fixing-size 10"

echo "=========================================="
echo "CLAW-Agent Date-Batched Pipeline Runner"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Start date: $START_DATE"
echo "  End date:   $END_DATE"
echo "  Verbose:    ${VERBOSE:-no}"
echo "  No tunnel:  ${NO_TUNNEL:-no}"
echo "  Filter:     ${FILTER:-no}"
echo ""
echo "The pipeline will run in one-month increments:"
echo "  - Each batch processes one month of data"
echo "  - Batches run sequentially (wait for completion)"
echo "  - All other options passed to each run"
echo ""
echo "=========================================="
echo ""

# Convert start and end dates to seconds since epoch for comparison
current_date="$START_DATE"
end_date_epoch=$(date -d "$END_DATE" +%s)

batch_count=0

while true; do
    # Calculate end of current batch (one month from current_date)
    batch_end=$(add_one_month "$current_date")
    
    # If batch_end exceeds the target end_date, use end_date instead
    if [[ "$batch_end" > "$END_DATE" ]]; then
        batch_end="$END_DATE"
    fi
    
    # Convert batch_end to epoch for comparison
    batch_end_epoch=$(date -d "$batch_end" +%s)
    
    # Check if we've reached or passed the end date
    if [ $batch_end_epoch -ge $end_date_epoch ]; then
        batch_end="$END_DATE"
        batch_end_epoch=$end_date_epoch
    fi
    
    # Check if current batch is valid (start < end)
    if [[ ! "$current_date" < "$batch_end" ]]; then
        echo "No more data to process. Ending batch loop."
        break
    fi
    
    batch_count=$((batch_count + 1))
    
    echo "=========================================="
    echo "Batch $batch_count: $current_date to $batch_end"
    echo "=========================================="
    echo ""
    
    # Build the command for this batch
    CMD="./scripts/run_pipeline.sh"
    CMD="$CMD --start-date $current_date --end-date $batch_end"
    CMD="$CMD $VERBOSE"
    CMD="$CMD $NO_TUNNEL"
    CMD="$CMD $FILTER"
    CMD="$CMD $AGENT"
    CMD="$CMD $EXTRACT_SIZE"
    CMD="$CMD $TAG_SIZE"
    CMD="$CMD $FILTER_SIZE"
    CMD="$CMD $VALIDATION_SIZE"
    CMD="$CMD $FIXING_SIZE"
    CMD="$CMD $HALLS"
    
    echo "Running: $CMD"
    echo ""
    
    # Run the pipeline for this batch
    eval $CMD
    
    if [ $? -ne 0 ]; then
        echo ""
        echo "=========================================="
        echo "ERROR: Batch $batch_count failed!"
        echo "Date range: $current_date to $batch_end"
        echo "=========================================="
        echo ""
        echo "Pipeline stopped. Fix the issue and resume manually if needed."
        exit 1
    fi
    
    echo ""
    echo "Batch $batch_count completed successfully!"
    echo ""
    
    # Check if we've reached the end
    if [ $batch_end_epoch -eq $end_date_epoch ]; then
        echo "=========================================="
        echo "All batches completed!"
        echo "Total batches processed: $batch_count"
        echo "=========================================="
        break
    fi
    
    # Move to next batch
    current_date="$batch_end"
    
    # Small delay between batches to avoid overwhelming the system
    echo "Waiting 5 seconds before next batch..."
    sleep 5
done

echo ""
echo "=========================================="
echo "Date-Batched Pipeline Complete!"
echo "Total batches: $batch_count"
echo "=========================================="