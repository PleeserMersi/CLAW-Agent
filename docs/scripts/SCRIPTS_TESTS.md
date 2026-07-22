# Mock Data Testing Suite

Reference for `scripts/run_all_tests.sh`.

---

## Overview

**Comprehensive testing suite** that runs the CLAW-Agent pipeline against mock data to evaluate accuracy, batch size performance, and parallel worker efficiency. Generates benchmark graphs and statistical reports.

**Location**: `scripts/run_all_tests.sh`

**Key Features**:
- Generates mock shift summaries if not present
- Tests multiple difficulty levels (easy, medium, hard)
- Tests batch sizes 1-20 (configurable)
- Tests parallel workers 1-10 (configurable)
- Runs multiple iterations per configuration (default: 10 runs)
- Generates accuracy and timing benchmark graphs
- Statistical analysis with mean ± standard deviation

---

## Usage

```bash
./scripts/run_all_tests.sh [OPTIONS]
```

---

## Options

| Option | Description |
|--------|-------------|
| `--verbose` | Enable verbose logging |
| `--force-regenerate` | Force regenerate mock data (deletes existing first) |
| `--runs N` | Number of runs per configuration (default: 10) |
| `--batch-only` | Run only batch size testing (ignores parallel sizes) |
| `--parallel-only` | Run only parallel workers testing (ignores batch sizes) |
| `--batch-sizes "N N N"` | Custom batch sizes (e.g., "1 2 4 8") |
| `--parallel-sizes "N N N"` | Custom parallel worker counts (e.g., "2 4 8") |
| `--help` | Show help message |

---

## Test Modes

### Comprehensive Mode (Default)

Runs both batch size and parallel worker testing:

```bash
./scripts/run_all_tests.sh
```

**What happens**:
- **Phase 1**: Batch sizes 1-20 for all difficulty levels (easy, medium, hard)
- **Phase 2**: Parallel workers 1-10 for medium difficulty (batch=5)
- **Runs**: 10 iterations per configuration
- **Output**: All benchmark graphs generated

**Estimated time**: Several hours (depends on LLM speed)

### Batch-Only Mode

Tests only batch size impact on accuracy:

```bash
./scripts/run_all_tests.sh --batch-only
```

**What happens**:
- Tests batch sizes 1-20 across all difficulty levels
- Ignores `--parallel-sizes` argument
- Generates batching accuracy and time graphs

**Custom batch sizes**:
```bash
./scripts/run_all_tests.sh --batch-only --batch-sizes "1 2 4 8 16"
```

### Parallel-Only Mode

Tests only parallel worker impact on performance:

```bash
./scripts/run_all_tests.sh --parallel-only
```

**What happens**:
- Tests parallel workers 1-10 for medium difficulty
- Fixed batch size: 5
- Ignores `--batch-sizes` argument
- Generates parallel workers benchmark graph

**Custom parallel sizes**:
```bash
./scripts/run_all_tests.sh --parallel-only --parallel-sizes "2 4 8"
```

---

## Difficulty Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| `easy` | Clear fault descriptions, simple timestamps | Baseline accuracy |
| `medium` | Moderate complexity, some ambiguity | Realistic performance |
| `hard` | Complex descriptions, tricky timestamps | Stress testing |

All levels are tested in comprehensive and batch-only modes.

---

## Examples

### Full Comprehensive Test (Default)

```bash
./scripts/run_all_tests.sh
```

Runs:
- Batch sizes 1-20 × 3 difficulty levels × 10 runs = 600 runs
- Parallel workers 1-10 × 10 runs = 100 runs
- Total: ~700 pipeline executions

### Quick Test with Custom Sizes

```bash
./scripts/run_all_tests.sh --batch-sizes "1 5 10" --parallel-sizes "2 4"
```

Runs:
- Batch sizes 1, 5, 10 × 3 levels × 10 runs = 90 runs
- Parallel workers 2, 4 × 10 runs = 20 runs
- Total: ~110 runs

### Batch-Only with Specific Sizes

```bash
./scripts/run_all_tests.sh --batch-only --batch-sizes "5 10 15"
```

Runs:
- Batch sizes 5, 10, 15 × 3 levels × 10 runs = 90 runs
- No parallel testing

### Parallel-Only with Custom Workers

```bash
./scripts/run_all_tests.sh --parallel-only --parallel-sizes "1 2 4 8"
```

Runs:
- Parallel workers 1, 2, 4, 8 × 10 runs = 40 runs
- Fixed batch size: 5, level: medium

### Fewer Runs for Speed

```bash
./scripts/run_all_tests.sh --runs 3
```

Reduces statistical significance but speeds up testing (3 runs instead of 10).

### Force Regenerate Mock Data

```bash
./scripts/run_all_tests.sh --force-regenerate
```

Deletes existing mock data and regenerates fresh samples.

### Verbose Logging

```bash
./scripts/run_all_tests.sh --verbose
```

Shows detailed output during pipeline execution.

---

## Execution Flow

### Step 1: Check/Generate Mock Data

```bash
[1/4] Checking mock data...
  Mock data already exists.
```

If mock data doesn't exist:
```
[1/4] Checking mock data...
  Generating mock data...
  Mock data generated.
```

**Location**: `testing/mock_summaries/`
**Files**: `mock_summaries_easy.csv`, `mock_summaries_medium.csv`, `mock_summaries_hard.csv`

### Step 2: Run Pipeline Tests

```bash
[2/4] Running pipeline tests...
  This may take several minutes or hours depending on configuration.
  The estimated time may vary depending on LLM speed.
  Estimated time: ~3 hours 15 minutes
```

**Time estimation**: Uses `calculate_time_estimate.py` for accurate estimates based on configuration.

### Step 3: Accuracy Evaluations

```bash
[3/4] Accuracy evaluations completed (included in pipeline run).
```

Accuracy checks run automatically during pipeline execution.

### Step 4: Generate Benchmarks

```bash
[4/4] Running benchmarks...
  Generating batching accuracy graphs...
  Generating batching time graphs...
  Generating parallel workers (batch=5) benchmark graphs...
  Benchmark graphs generated in testing/benchmarks/graphs/
```

**Graphs generated**:
- `batching_accuracy.png` - Accuracy vs batch size by difficulty
- `batching_time.png` - Execution time vs batch size
- `parallel_workers_batch5.png` - Performance vs parallel workers

---

## Output Files

### Pipeline Output

**Location**: `testing/pipeline_output/`

| File | Description |
|------|-------------|
| `test_summary.json` | Overall test summary |
| `accuracy_report_easy_batch1.json` | Accuracy report for easy, batch=1 |
| `accuracy_report_medium_batch5.json` | Accuracy report for medium, batch=5 |
| `accuracy_report_hard_batch10.json` | Accuracy report for hard, batch=10 |
| ... | One report per configuration |

### Benchmark Graphs

**Location**: `testing/benchmarks/graphs/`

| Graph | Description |
|-------|-------------|
| `batching_accuracy.png` | Accuracy vs batch size with error bars |
| `batching_time.png` | Execution time vs batch size |
| `parallel_workers_batch5.png` | Performance vs parallel workers |

### Raw Data

**Location**: `testing/benchmarks/`

| File | Description |
|------|-------------|
| `accuracy_data.json` | Aggregated accuracy data |
| `timing_data.json` | Aggregated timing data |

---

## Viewing Results

### Test Summary

```bash
cat testing/pipeline_output/test_summary.json
```

### Specific Accuracy Report

```bash
cat testing/pipeline_output/accuracy_report_medium_batch5.json
```

### List Generated Graphs

```bash
ls -la testing/benchmarks/graphs/
```

### View Graphs

Open PNG files in image viewer:
```bash
xdg-open testing/benchmarks/graphs/batching_accuracy.png  # Linux
open testing/benchmarks/graphs/batching_accuracy.png      # macOS
```

---

## Virtual Environment

The script automatically manages the virtual environment:

1. **Check for existing venv**:
   ```bash
   if [ -f "$VENV_DIR/bin/activate" ]; then
       source "$VENV_DIR/bin/activate"
   ```

2. **Create if missing**:
   ```bash
   else
       python3 -m venv "$VENV_DIR"
       source "$VENV_DIR/bin/activate"
       pip install --upgrade pip
       pip install -r requirements.txt
   ```

---

## Performance Considerations

### Estimated Time Calculation

Time is estimated using `testing/calculate_time_estimate.py` which accounts for:
- Number of batch sizes × difficulty levels × runs
- Number of parallel sizes × runs
- Average LLM response time

**Fallback estimation** (if Python script fails):
- ~5 minutes per run (conservative estimate)
- Total = (total configs × runs) × 5 minutes

### Memory Usage

- Larger batch sizes = more memory during parallel processing
- Recommended: start with batch sizes 1-10 for testing
- Use `--batch-sizes "1 2 4 8"` for quick tests

### Parallel Workers

- More workers = faster execution but higher memory usage
- Recommended: test 1-5 workers for most systems
- Use `--parallel-sizes "1 2 4"` for quick tests

---

## Troubleshooting

### Mock Data Generation Fails

```bash
# Check Python dependencies
cd testing/mock_summaries
python3 generate_summaries.py

# Force regeneration
./scripts/run_all_tests.sh --force-regenerate
```

### Benchmark Graphs Not Generated

```bash
# Check if accuracy data exists
ls testing/benchmarks/accuracy_data.json

# Run pipeline manually if needed
cd testing
python3 run_mock_pipeline.py --all-tests
```

### Tests Take Too Long

```bash
# Reduce runs per configuration
./scripts/run_all_tests.sh --runs 3

# Test only specific batch sizes
./scripts/run_all_tests.sh --batch-only --batch-sizes "1 5 10"

# Test only specific parallel sizes
./scripts/run_all_tests.sh --parallel-only --parallel-sizes "2 4"
```

### Virtual Environment Issues

```bash
# Recreate venv
rm -rf venv
./scripts/run_all_tests.sh  # Will recreate venv
```

---

## Related Documentation

- [Developer Testing](../getting-started/DEVELOPER_TESTING.md) - Testing guidelines
- [Operations](../pipeline/OPERATIONS_PIPELINE.md) - Pipeline operations
- [Configuration](../config/CONFIGURATION.md) - Pipeline configuration

---

*For testing guidelines, see [DEVELOPER_TESTING.md](../getting-started/DEVELOPER_TESTING.md).*