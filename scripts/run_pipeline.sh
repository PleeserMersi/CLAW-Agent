#!/bin/bash
# CLAW-Agent Pipeline Runner
#
# Runs the main fault extraction pipeline with date range defaults:
# - Start date: 2 days ago
# - End date: 1 day ago
#
# Usage:
#   ./run_pipeline.sh                           # Use default dates (2 days ago to 1 day ago)
#   ./run_pipeline.sh --start-date 2024-01-01   # Custom start date
#   ./run_pipeline.sh --end-date 2024-01-15     # Custom end date
#   ./run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-31
#   ./run_pipeline.sh --verbose                 # Enable verbose logging

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Project root is the parent of scripts folder
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to project root
cd "$PROJECT_ROOT"

# Activate virtual environment if it exists
VENV_DIR="$PROJECT_ROOT/venv"
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
else
    echo "Virtual environment not found at $VENV_DIR"
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    
    echo "Installing dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r "$PROJECT_ROOT/requirements.txt"
    
    echo "Virtual environment setup complete."
fi

# Calculate default dates (2 days ago to 1 day ago)
# Using date command for portability
START_DATE=$(date -d "2 days ago" +%Y-%m-%d)
END_DATE=$(date -d "1 day ago" +%Y-%m-%d)

# Parse arguments
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
            echo "Usage: ./run_pipeline.sh [OPTIONS]"
            echo ""
            echo "Runs the CLAW-Agent fault extraction pipeline."
            echo ""
            echo "Date Options:"
            echo "  --start-date YYYY-MM-DD  Start date (default: 2 days ago: $START_DATE)"
            echo "  --end-date YYYY-MM-DD    End date (default: 1 day ago: $END_DATE)"
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
            echo "  --halls HALL1 [HALL2...]  Hall(s) to process (hall_a, hall_b, hall_c, hall_d)"
            echo ""
            echo "Examples:"
            echo "  ./run_pipeline.sh                           # Default: 2 days ago to 1 day ago"
            echo "  ./run_pipeline.sh --start-date 2024-01-01   # Custom start date"
            echo "  ./run_pipeline.sh --verbose                 # Verbose logging"
            echo "  ./run_pipeline.sh --extract-size 10 --tag-size 20  # Custom batch sizes"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "CLAW-Agent Pipeline Runner"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Start date: $START_DATE"
echo "  End date:   $END_DATE"
echo "  Verbose:    ${VERBOSE:-no}"
echo "  No tunnel:  ${NO_TUNNEL:-no}"
echo "  Filter:     ${FILTER:-no}"
echo ""
echo "Running pipeline..."
echo "=========================================="
echo ""

# Build the command
CMD="python3 src/pipeline.py"
CMD="$CMD --start-date $START_DATE --end-date $END_DATE"

# Set default batch sizes if not provided
[ -z "$EXTRACT_SIZE" ] && EXTRACT_SIZE="--extract-size 5"
[ -z "$TAG_SIZE" ] && TAG_SIZE="--tag-size 10"
[ -z "$FILTER_SIZE" ] && FILTER_SIZE="--filter-size 10"
[ -z "$VALIDATION_SIZE" ] && VALIDATION_SIZE="--validation-size 10"
[ -z "$FIXING_SIZE" ] && FIXING_SIZE="--fixing-size 10"

# Add optional arguments if set
[ -n "$VERBOSE" ] && CMD="$CMD $VERBOSE"
[ -n "$NO_TUNNEL" ] && CMD="$CMD $NO_TUNNEL"
[ -n "$FILTER" ] && CMD="$CMD $FILTER"
[ -n "$AGENT" ] && CMD="$CMD $AGENT"
CMD="$CMD $EXTRACT_SIZE $TAG_SIZE $FILTER_SIZE $VALIDATION_SIZE $FIXING_SIZE"
[ -n "$HALLS" ] && CMD="$CMD $HALLS"

# Run the pipeline
echo "Command: $CMD"
echo ""
eval $CMD

echo ""
echo "=========================================="
echo "Pipeline Complete!"
echo "=========================================="
