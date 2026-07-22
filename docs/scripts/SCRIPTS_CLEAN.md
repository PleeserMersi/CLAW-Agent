# Clean Data Script

Reference for `scripts/clean_data.sh`.

---

## Overview

Interactive cleanup script that removes temporary files, cache, and testing output while **always preserving final output**. Requires manual confirmation before deletion.

**Location**: `scripts/clean_data.sh`

**Key Features**:
- Interactive confirmation prompt (no accidental deletions)
- Removes temporary CSV, JSON, and backup files
- Cleans `__pycache__` directories
- Resets ChromaDB embeddings
- Clears testing pipeline output
- **Always preserves** `data/final_output/`

---

## Usage

```bash
./scripts/clean_data.sh
```

**No options** - runs in single mode with interactive confirmation.

---

## What Gets Cleaned

### Files Removed

#### Data Directory (`data/`)
- `data/raw/*.csv`, `*.json`, `*.JSON`, `*.backup` - Raw API responses
- `data/processed/*.csv`, `*.json` - Intermediate processing outputs
- `data/verified/*.csv`, `*.json` - Verified fault splits
- `data/fixed/*.csv`, `*.json` - Fixed timestamp data

**Excluded**: All files in `data/final_output/` are **never removed**.

#### Python Cache
- All `__pycache__/` directories project-wide
- **Excluded**: `venv/` directory is preserved

#### Tag Database
- `tag_db/chroma_db/` - ChromaDB vector embeddings directory
- Will be rebuilt on next pipeline run

#### Testing Output
- `testing/pipeline_output/*` - All pipeline test outputs
- `testing/mock_summaries/*/SUMMARY.txt` - Mock summary files
- `testing/*.png` - Test graphs and visualizations
- `testing/*.csv`, `*.json` - Test data files
- **Excluded**: `accuracy_report_medium_vs_real.csv.json` (preserved)

### Files Preserved

✅ **Always kept**:
- `data/final_output/*.csv` - Final pipeline output
- `data/final_output/*.json` - Any final output files
- `venv/` - Python virtual environment
- `accuracy_report_medium_vs_real.csv.json` - Specific test artifact

---

## Execution Flow

### Step 1: Scan Files

Script scans and lists all files that would be deleted:

```
Cleaning temporary files in /home/user/CLAW-Agent/data...
Also cleaning __pycache__ directories, tag_db/chroma_db, and testing output...
Preserving: data/final_output/

Found 15 temporary file(s) to delete in data/:
  data/raw/2026-07-15_shifts.csv
  data/processed/extracted_faults.csv
  data/verified/accurate_faults.csv
  ...

Found 3 __pycache__ directory/directories to delete:
  src/analysis/__pycache__
  src/data/__pycache__
  src/utils/__pycache__

Found chroma_db directory to delete:
  tag_db/chroma_db

Found 8 testing output file(s) to delete:
  testing/pipeline_output/results.csv
  testing/mock_summaries/test1/SUMMARY.txt
  testing/graphs/fault_distribution.png
  ...
```

### Step 2: Confirmation Prompt

```
Delete these files? [y/N] 
```

- Press `y` + Enter to proceed
- Press any other key (or Enter) to cancel

### Step 3: Deletion

If confirmed, script deletes all listed files and shows summary:

```
Deleted 15 temporary file(s), 3 __pycache__ directory/directories, chroma_db, and 8 testing output file(s).

Preserved files in data/final_output/:
  data/final_output/all_shift_faults.csv
  data/final_output/manual_check.csv
```

---

## Examples

### Run Cleanup

```bash
./scripts/clean_data.sh
```

Script will:
1. List all files to be deleted
2. Prompt for confirmation
3. Delete files if confirmed
4. Show preserved files

### Cancel Cleanup

```bash
./scripts/clean_data.sh
# Press Enter or any key except 'y' when prompted
```

Output:
```
Cancelled.
```

---

## Safety Features

### Interactive Confirmation

**Requires manual approval** before any deletion occurs. This prevents accidental data loss.

### Always Preserves Final Output

The script **never** removes files in `data/final_output/`, regardless of what else is cleaned.

### Excludes Virtual Environment

`venv/` directory is explicitly excluded from `__pycache__` cleanup.

### Preserves Key Test Artifacts

`accuracy_report_medium_vs_real.csv.json` is preserved for comparison studies.

---

## When to Use

### Run Cleanup When:
- Disk space is running low
- Starting fresh debugging session
- Testing pipeline from scratch
- Removing stale intermediate data
- Clearing corrupted cache

### Skip Cleanup When:
- You need to re-run analysis on same data
- Preserving intermediate results for comparison
- Debugging specific pipeline stage
- Final output hasn't been backed up

---

## Manual Alternative

If you prefer manual control, these commands achieve the same cleanup:

```bash
# Remove temporary data files (preserve final output)
find data/ \( -name "*.csv" -o -name "*.json" -o -name "*.backup" \) -type f ! -path "data/final_output/*" -delete

# Remove __pycache__ (exclude venv)
find . -path ./venv -prune -o -type d -name "__pycache__" -exec rm -rf {} +

# Remove ChromaDB
rm -rf tag_db/chroma_db

# Remove testing output
find testing/ \( -name "*.png" -o -path "testing/pipeline_output/*" \) -type f -delete
```

---

## Related Documentation

- [Operations](../pipeline/OPERATIONS_PIPELINE.md) - Data management
- [Output Formats](../config/OUTPUT_FORMATS.md) - File structure
- [Pipeline Runner](./SCRIPTS_PIPELINE.md) - Main pipeline script

---

*For data management strategies, see [OPERATIONS_PIPELINE.md](../pipeline/OPERATIONS_PIPELINE.md).*