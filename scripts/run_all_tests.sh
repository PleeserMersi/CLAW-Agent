#!/bin/bash
# CLAW-Agent Mock Data Testing Suite - Full Test Runner
#
# This script runs the complete testing pipeline:
# 1. Generates mock data (if needed)
# 2. Runs CLAW-Agent pipeline with all difficulty levels and batch sizes
# 3. Runs accuracy evaluations
# 4. Generates benchmark graphs
#
# Usage:
#   ./run_all_tests.sh                    # Run comprehensive all-tests mode
#   ./run_all_tests.sh --batch-only       # Run only batch size testing (1-20)
#   ./run_all_tests.sh --parallel-only    # Run only parallel workers testing
#   ./run_all_tests.sh --verbose          # Add verbose logging
#   ./run_all_tests.sh --batch-sizes "1 2 4 8"  # Custom batch sizes

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The testing folder is a sibling of this script's directory
TESTING_DIR="$(cd "$SCRIPT_DIR/../testing" && pwd)"

# Project root is the parent of scripts folder
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Change to the testing directory for execution
cd "$TESTING_DIR"

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

# Default mode: comprehensive all-tests
MODE="comprehensive"
VERBOSE=""
BATCH_SIZES="1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20"
PARALLEL_SIZES="1 2 3 4 5 6 7 8 9 10"
LEVELS="easy medium hard"
RUNS=10  # Default number of runs per configuration for statistical significance
RUNS_ARG="--runs $RUNS"  # Always pass runs argument to Python

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose)
            VERBOSE="--verbose"
            shift
            ;;
        --force-regenerate)
            FORCE_REGEN="--force-regenerate"
            shift
            ;;
        --runs)
            RUNS="$2"
            RUNS_ARG="--runs $2"
            shift 2
            ;;
        --batch-only)
            MODE="batch_only"
            shift
            ;;
        --parallel-only)
            MODE="parallel_only"
            shift
            ;;
        --parallel-sizes)
            PARALLEL_SIZES="$2"
            # Don't auto-switch mode here - let user control mode explicitly
            shift 2
            ;;
        --batch-sizes)
            BATCH_SIZES="$2"
            # Don't auto-switch mode here - let user control mode explicitly
            shift 2
            ;;
        --help)
            echo "Usage: ./run_all_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --verbose          Enable verbose logging"
            echo "  --force-regenerate Force regenerate mock data (deletes existing first)"
            echo "  --runs <n>         Number of runs per configuration (default: $RUNS)"
            echo "  --batch-only       Run only batch size testing (ignores --parallel-sizes)"
            echo "  --parallel-only    Run only parallel workers testing (ignores --batch-sizes)"
            echo "  --parallel-sizes   Custom parallel worker counts (e.g., '1 2 4 8')"
            echo "  --batch-sizes      Custom batch sizes (e.g., '1 2 4 8')"
            echo "  --help             Show this help message"
            echo ""
            echo "Argument Independence:"
            echo "  - --batch-sizes and --parallel-sizes are independent and can be combined"
            echo "  - --batch-only ignores --parallel-sizes (runs only batch tests)"
            echo "  - --parallel-only ignores --batch-sizes (runs only parallel tests)"
            echo "  - Without --batch-only/--parallel-only, both size arguments are used (comprehensive mode)"
            echo ""
            echo "Examples:"
            echo "  ./run_all_tests.sh                           # Comprehensive: batch 1-20 + parallel 1-10"
            echo "  ./run_all_tests.sh --batch-sizes '5 10 15'   # Comprehensive: batch 5,10,15 + parallel 1-10"
            echo "  ./run_all_tests.sh --parallel-sizes '2 4 8'  # Comprehensive: batch 1-20 + parallel 2,4,8"
            echo "  ./run_all_tests.sh --batch-sizes '10' --parallel-sizes '4'  # Comprehensive: batch 10 + parallel 4"
            echo "  ./run_all_tests.sh --batch-only --batch-sizes '5 10'        # Batch-only: 5,10 (ignores parallel)"
            echo "  ./run_all_tests.sh --parallel-only --parallel-sizes '2 4'   # Parallel-only: 2,4 (ignores batch)"
            echo ""
            echo "Default (no args): Runs comprehensive all-tests mode:"
            echo "  - Phase 1: Batch sizes 1-20 for all difficulties ($RUNS runs each)"
            echo "  - Phase 2: Parallel workers 1-10 for medium difficulty (batch=5, $RUNS runs each)"
            echo "  - Auto-generates all benchmark graphs with mean ± std deviation"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=========================================="
echo "CLAW-Agent Mock Data Testing Suite"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Mode: $MODE"
if [ "$MODE" == "comprehensive" ]; then
    echo "  Phase 1: Batch sizes $BATCH_SIZES for all difficulties ($RUNS runs each)"
    echo "  Phase 2: Parallel workers ($PARALLEL_SIZES) for medium (batch=5, $RUNS runs each)"
elif [ "$MODE" == "batch_only" ]; then
    echo "  Batch sizes: $BATCH_SIZES"
    echo "  Levels: $LEVELS"
    echo "  Runs per config: $RUNS"
    echo "  (Note: --parallel-sizes is ignored in batch-only mode)"
elif [ "$MODE" == "parallel_only" ]; then
    echo "  Parallel workers: $PARALLEL_SIZES"
    echo "  Batch size: 5"
    echo "  Level: medium"
    echo "  Runs per config: $RUNS"
    echo "  (Note: --batch-sizes is ignored in parallel-only mode)"
fi
echo "  Verbose: ${VERBOSE:-no}"
echo "  Runs per configuration: $RUNS"
echo ""

# Step 1: Generate mock data if not exists
echo "[1/4] Checking mock data..."
MOCK_EASY="$TESTING_DIR/mock_summaries/mock_summaries_easy.csv"

if [ ! -f "$MOCK_EASY" ]; then
    echo "  Generating mock data..."
    cd "$TESTING_DIR/mock_summaries"
    python3 generate_summaries.py
    cd "$TESTING_DIR"
    echo "  Mock data generated."
else
    echo "  Mock data already exists."
fi

# Step 2: Run pipeline tests
echo ""
echo "[2/4] Running pipeline tests..."

# Calculate estimated time using the time data file
BATCH_ARG=""
for size in $BATCH_SIZES; do
    BATCH_ARG="$BATCH_ARG,$size"
done
BATCH_ARG=${BATCH_ARG#,}  # Remove leading comma

PARALLEL_ARG=""
for size in $PARALLEL_SIZES; do
    PARALLEL_ARG="$PARALLEL_ARG,$size"
done
PARALLEL_ARG=${PARALLEL_ARG#,}  # Remove leading comma

# Use Python script to calculate accurate time estimate
EST_TIME=$(python3 "$TESTING_DIR/calculate_time_estimate.py" "$BATCH_ARG" "$PARALLEL_ARG" "$RUNS" 2>/dev/null)

if [ -z "$EST_TIME" ] || [ "$EST_TIME" = "Error" ]; then
    # Fallback to simple estimation if Python script fails
    if [ "$MODE" == "comprehensive" ]; then
        BATCH_COUNT=$(echo $BATCH_SIZES | wc -w)
        PARALLEL_COUNT=$(echo $PARALLEL_SIZES | wc -w)
        TOTAL_CONFIGS=$((BATCH_COUNT * 3 + PARALLEL_COUNT))
    elif [ "$MODE" == "batch_only" ]; then
        BATCH_COUNT=$(echo $BATCH_SIZES | wc -w)
        TOTAL_CONFIGS=$((BATCH_COUNT * 3))
    else
        TOTAL_CONFIGS=$(echo $PARALLEL_SIZES | wc -w)
    fi
    TOTAL_RUNS=$((TOTAL_CONFIGS * RUNS))
    EST_MINUTES=$((TOTAL_RUNS * 5))
    if [ $EST_MINUTES -lt 60 ]; then
        EST_TIME="~${EST_MINUTES} minutes"
    else
        EST_HOURS=$((EST_MINUTES / 60))
        EST_REM_MIN=$((EST_MINUTES % 60))
        if [ $EST_REM_MIN -eq 0 ]; then
            EST_TIME="~${EST_HOURS} hours"
        else
            EST_TIME="~${EST_HOURS} hours ${EST_REM_MIN} minutes"
        fi
    fi
fi

echo "  This may take several minutes or hours depending on configuration."
echo "  The estimated time may vary depending on LLM speed."
echo "  Estimated time: $EST_TIME"

if [ "$MODE" == "comprehensive" ]; then
    # Comprehensive mode: use --all-tests with custom sizes
    # Build batch sizes argument
    BATCH_ARG=""
    for size in $BATCH_SIZES; do
        BATCH_ARG="$BATCH_ARG $size"
    done
    
    # Build parallel sizes argument
    PARALLEL_ARG=""
    for size in $PARALLEL_SIZES; do
        PARALLEL_ARG="$PARALLEL_ARG $size"
    done
    
    python3 run_mock_pipeline.py \
        --all-tests \
        --levels $LEVELS \
        --batch-sizes $BATCH_ARG \
        --parallel-workers $PARALLEL_ARG \
        $RUNS_ARG \
        $FORCE_REGEN \
        $VERBOSE
elif [ "$MODE" == "batch_only" ]; then
    # Batch-only mode
    BATCH_ARG=""
    for size in $BATCH_SIZES; do
        BATCH_ARG="$BATCH_ARG $size"
    done
    
    python3 run_mock_pipeline.py \
        --levels $LEVELS \
        --batch-sizes $BATCH_ARG \
        $RUNS_ARG \
        $FORCE_REGEN \
        $VERBOSE
elif [ "$MODE" == "parallel_only" ]; then
    # Parallel-only mode with custom worker counts
    PARALLEL_ARG=""
    for size in $PARALLEL_SIZES; do
        PARALLEL_ARG="$PARALLEL_ARG $size"
    done
    
    python3 run_mock_pipeline.py \
        --levels medium \
        --parallel-workers $PARALLEL_ARG \
        --batch-size 5 \
        $RUNS_ARG \
        $FORCE_REGEN \
        $VERBOSE
fi

# Step 3: Run accuracy evaluations (included in step 2)
echo ""
echo "[3/4] Accuracy evaluations completed (included in pipeline run)."

# Step 4: Run benchmarks
echo ""
echo "[4/4] Running benchmarks..."
cd "$TESTING_DIR/benchmarks"

# Check if we have accuracy data
if [ -f "accuracy_data.json" ]; then
    if [ "$MODE" == "comprehensive" ] || [ "$MODE" == "batch_only" ]; then
        echo "  Generating batching accuracy graphs..."
        python3 batching_accuracy.py || echo "  Note: batching_accuracy.py may need data adjustments"
        
        echo "  Generating batching time graphs..."
        python3 batching_time.py || echo "  Note: batching_time.py may need data adjustments"
    fi
    
    if [ "$MODE" == "comprehensive" ] || [ "$MODE" == "parallel_only" ]; then
        echo "  Generating parallel workers (batch=5) benchmark graphs..."
        python3 parallel_workers_batch5.py || echo "  Note: parallel_workers_batch5.py may need data adjustments"
    fi
    
    echo "  Benchmark graphs generated in $TESTING_DIR/benchmarks/graphs/"
else
    echo "  No accuracy data found. Skipping benchmarks."
    echo "  Run pipeline first with: python3 run_mock_pipeline.py"
fi

cd "$TESTING_DIR"

echo ""
echo "=========================================="
echo "All Tests Complete!"
echo "=========================================="
echo ""
echo "Results saved to:"
echo "  - $TESTING_DIR/pipeline_output/test_summary.json"
echo "  - $TESTING_DIR/pipeline_output/accuracy_report_*.json"
echo "  - $TESTING_DIR/benchmarks/graphs/*.png"
echo ""
echo "View summary:"
echo "  cat pipeline_output/test_summary.json"
echo ""
echo "View specific accuracy report:"
echo "  cat pipeline_output/accuracy_report_easy_batch1.json"
echo ""
echo "View graphs:"
echo "  ls -la benchmarks/graphs/"
echo ""