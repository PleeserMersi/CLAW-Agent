# Testing Guide

Developer guide for testing CLAW-Agent using the mock data testing framework.

---

## Test Structure

The project uses a custom testing framework located in the `testing/` directory, which runs mock data through the pipeline and evaluates accuracy.

### Main Testing Components

**Location**: `testing/`

**Key Files**:
- `run_mock_pipeline.py` - Main test runner that executes the pipeline with mock data
- `test_config.py` - Test configuration and parameters
- `accuracy_tester/` - Accuracy evaluation module
- `benchmarks/` - Performance benchmarking tools
- `mock_summaries/` - Pre-generated mock shift summaries
- `pipeline_output/` - Expected output comparisons
- `tag_db/` - Tag database for validation

### Test Data Structure

**Location**: `testing/test_data/`

**Subdirectories**:
- `raw/` - Input mock shift summaries
- `processed/` - Intermediate pipeline outputs
- `final_output/` - Complete pipeline results
- `verified/` - Manually verified correct outputs
- `fixed/` - Corrected outputs after fixer stage

---

## Running Tests

### Full Test Suite

Run the comprehensive testing pipeline (generates mock data, runs all difficulty levels and batch sizes, evaluates accuracy, generates benchmarks):

```bash
./scripts/run_all_tests.sh
```

### Test Suite Options

```bash
# Batch size testing only (batches 1-20)
./scripts/run_all_tests.sh --batch-only

# Parallel workers testing only
./scripts/run_all_tests.sh --parallel-only

# Add verbose logging
./scripts/run_all_tests.sh --verbose

# Custom batch sizes
./scripts/run_all_tests.sh --batch-sizes "1 2 4 8"
```

### Direct Pipeline Execution

Run the mock pipeline directly with custom parameters:

```bash
cd testing
python3 run_mock_pipeline.py --difficulty easy --batch-size 4
```

---

## Test Data

**Location**: `testing/test_data/`

**Contents**:
- `raw/` - Sample shift summaries for input
- `verified/` - Ground truth outputs for comparison
- `fixed/` - Corrected outputs from the fixer module
- `processed/` - Intermediate processing results
- `final_output/` - Final pipeline outputs

**Mock Data Generation**:
- `mock_summaries/` - Pre-generated mock shift summaries
- Mock data is automatically generated if not present when running tests

---

## Testing Workflow

### 1. Mock Data Generation

The test framework automatically generates mock shift summaries with varying:
- Difficulty levels (easy, medium, hard)
- Batch sizes (configurable)
- Fault types and complexity

### 2. Pipeline Execution

Tests run the full CLAW-Agent pipeline:
1. Data loading from mock summaries
2. Fault extraction
3. Tag classification
4. Link generation
5. Fixer corrections (if enabled)
6. Verification

### 3. Accuracy Evaluation

The `accuracy_tester/` module compares outputs against:
- Verified ground truth data
- Expected tag classifications
- Correct link structures

### 4. Benchmarking

Performance metrics collected:
- Processing time per batch size
- Memory usage
- Accuracy scores by difficulty level

---

## Manual Testing

### Test Specific Components

**Test tag extraction**:
```bash
cd testing
python3 -c "from src.analysis.tag_extraction import get_candidate_tags; print(get_candidate_tags('RF cavity trip'))"
```

**Test text utilities**:
```bash
cd testing
python3 -c "from src.utils.text_utils import normalize_timestamp; print(normalize_timestamp('2:30 PM'))"
```

**Run accuracy tests**:
```bash
cd testing/accuracy_tester
python3 evaluate.py
```

---

## Test Configuration

**Location**: `testing/test_config.py`

Configure test parameters:
- Default batch sizes
- Difficulty levels to test
- Parallel worker counts
- Output verbosity

---

## Troubleshooting

### Common Issues

**Mock data generation fails**:
- Check `testing/mock_summaries/` has write permissions
- Verify LLM API keys are set in `.env`

**Accuracy evaluation shows low scores**:
- Review `testing/test_data/verified/` for correct reference outputs
- Check if the fixer module is enabled in test configuration

**Pipeline crashes mid-run**:
- Check `testing/pipeline_output/` for partial results
- Review logs in `src/utils/logging_utils.py` output

---

## Related Documentation

- [Scripts](./SCRIPTS_TESTS.md) - Test runner script details
- [Pipeline](./PIPELINE_OVERVIEW.md) - Pipeline architecture

---

*For test runner script details, see [SCRIPTS_TESTS.md](./SCRIPTS_TESTS.md).*