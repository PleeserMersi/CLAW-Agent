# Consolidation Pipeline

Detailed documentation for the final consolidation stage of CLAW-Agent.

---

## Overview

The consolidation stage merges verified (accurate) and fixed faults into a single final output file. This is the last pipeline stage before dashboard visualization.

**Module**: `src/analysis/verifyer.py`

**Pipeline Position**: Stage 5 (final stage)

**Input**: 
- `data/verified/accurate.csv` - Faults with verified timestamps
- `data/fixed/fixed.csv` - Faults with corrected timestamps

**Output**: 
- `data/final_output/all_shift_faults.csv` - Final merged output (appended each run)

**Key Behavior**: 
- Appends to existing output (preserves history across runs)
- Ensures all expected columns present (fills missing with None)
- Sorts by `FullTimestamp`
- `agent` parameter accepted but unused (merge operation)

---

## Consolidation Process

### Merge Strategy

```python
def consolidate_faults(agent: str = None) -> Optional[pd.DataFrame]:
    all_faults = []
    
    # Load accurate faults (with error handling)
    if ACCURATE_CSV.exists():
        try:
            accurate_df = pd.read_csv(ACCURATE_CSV)
            accurate_df['verification_status'] = 'accurate'
            all_faults.append(accurate_df)
        except Exception as e:
            logger.error(f"Failed to load accurate faults: {e}")
    
    # Load fixed faults (with error handling)
    if FIXED_CSV.exists():
        try:
            fixed_df = pd.read_csv(FIXED_CSV)
            fixed_df['verification_status'] = 'fixed'
            all_faults.append(fixed_df)
        except Exception as e:
            logger.error(f"Failed to load fixed faults: {e}")
    
    if not all_faults:
        logger.warning("No verified or fixed faults found")
        return pd.DataFrame()
    
    # Combine all faults
    combined_df = pd.concat(all_faults, ignore_index=True)
    
    # Ensure all expected columns exist (fill missing with None)
    expected_cols = [
        'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
        'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 
        'ShiftHall', 'FragmentLink', 'verification_status'
    ]
    for col in expected_cols:
        if col not in combined_df.columns:
            combined_df[col] = None
    
    # Reorder columns to match expected schema
    combined_df = combined_df[[col for col in expected_cols if col in combined_df.columns]]
    
    # Sort by timestamp
    if 'FullTimestamp' in combined_df.columns:
        combined_df = combined_df.sort_values('FullTimestamp')
    
    return combined_df
```

**Key Features**:
- **Error handling**: Try/except for each file load (continues if one fails)
- **Column normalization**: Ensures all expected columns exist
- **Column ordering**: Reorders to match expected schema
- **Empty result**: Returns empty DataFrame if no faults found

### Output Schema

**File**: `data/final_output/all_shift_faults.csv`

**Columns**:

| Column | Type | Description |
|--------|------|-------------|
| `FullTimestamp` | datetime | Combined date + time |
| `timestamp` | str | Time (HH:MM) |
| `description` | str | Fault description |
| `tag` | str | Assigned tag |
| `run_number` | str | Run number (if available) |
| `ShiftLogNumber` | int | Logbook entry number |
| `ShiftLogbookURL` | str | URL to logbook |
| `ShiftTitle` | str | Shift summary title |
| `ShiftDateTime` | str | Summary creation time |
| `ShiftHall` | str | Hall name |
| `FragmentLink` | str | Clickable timestamp link |
| `verification_status` | str | "accurate" or "fixed" |

---

## Append vs. Overwrite

### Append Mode

**Behavior**: New runs append to existing `all_shift_faults.csv`

**Rationale**:
- Preserve historical data across multiple pipeline runs
- Avoid losing previous runs
- Enable incremental processing (e.g., daily runs build cumulative dataset)

**Implementation**:
```python
# Create output directory if needed
ALL_FAULTS_CSV.parent.mkdir(parents=True, exist_ok=True)

if ALL_FAULTS_CSV.exists() and ALL_FAULTS_CSV.stat().st_size > 0:
    # Append to existing file (no header)
    combined_df.to_csv(ALL_FAULTS_CSV, mode='a', index=False, header=False)
    logger.info(f"Appended {len(combined_df)} verified faults")
else:
    # Create new file with header
    combined_df.to_csv(ALL_FAULTS_CSV, mode='w', index=False, header=True)
    logger.info(f"Created {ALL_FAULTS_CSV} with {len(combined_df)} faults")
```

**Note**: Each run appends its verified faults. To start fresh, manually delete the file.

### Clearing Output

**To start fresh**:
```bash
rm data/final_output/all_shift_faults.csv
rm data/final_output/manual_check.csv
```

---

## Output Files

### Final Outputs

| File | Location | Purpose | Contents |
|------|----------|---------|----------|
| `all_shift_faults.csv` | `data/final_output/` | Primary output | All verified faults (accurate + fixed), appended each run |
| `manual_check.csv` | `data/fixed/` | Review queue | Low-confidence fixes + fixes that failed re-verification |

**Note**: `manual_check.csv` is created by the fixing stage (`fixer.py`), not consolidation. It contains:
- Faults where timestamp couldn't be extracted
- Faults with low-confidence fixes (failed re-verification)
- Faults from the inaccurate set that weren't successfully fixed

### Intermediate Files

| File | Location | Purpose | Created By |
|------|----------|---------|------------|
| `accurate.csv` | `data/verified/` | Faults with verified timestamps | `accuracy_test.py` |
| `inaccurate.csv` | `data/verified/` | Faults needing timestamp correction | `accuracy_test.py` |
| `fixed.csv` | `data/fixed/` | Successfully fixed timestamps | `fixer.py` |
| `processed_summaries.csv` | `data/processed/` | Faults after extraction + tagging | `shift_summary.py` |

**Cleanup Behavior**: 
- Pipeline deletes all intermediate CSVs/JSONs in `data/` before each run (except `final_output/`)
- `all_shift_faults.csv` and `manual_check.csv` are preserved (in `final_output/` or handled specially)
- To preserve intermediate files, copy them before running pipeline

---

## Usage Examples

### Basic Consolidation

```python
from src.analysis.verifyer import final_verification

# Consolidate (agent parameter accepted but unused)
final_df = final_verification(agent="fault_analyst")

if final_df is not None and len(final_df) > 0:
    print(f"Total faults: {len(final_df)}")
    print(f"Accurate: {len(final_df[final_df['verification_status'] == 'accurate'])}")
    print(f"Fixed: {len(final_df[final_df['verification_status'] == 'fixed'])}")
else:
    print("No verified faults found")
```

### Load Final Output

```python
import pandas as pd

df = pd.read_csv("data/final_output/all_shift_faults.csv")

print(f"Total faults: {len(df)}")
print(f"Date range: {df['FullTimestamp'].min()} to {df['FullTimestamp'].max()}")
print(f"Tag distribution:\n{df['tag'].value_counts()}")
print(f"Status breakdown:\n{df['verification_status'].value_counts()}")
```

---

## Quality Assurance

### Completeness Check

**Verify all faults accounted for**:
```python
import pandas as pd

accurate_df = pd.read_csv("data/verified/accurate.csv") if Path("data/verified/accurate.csv").exists() else pd.DataFrame()
fixed_df = pd.read_csv("data/fixed/fixed.csv") if Path("data/fixed/fixed.csv").exists() else pd.DataFrame()

# Note: final output is appended, so check recent run only or track counts separately
accurate_count = len(accurate_df)
fixed_count = len(fixed_df)
expected_total = accurate_count + fixed_count

print(f"Accurate: {accurate_count}, Fixed: {fixed_count}, Expected total: {expected_total}")
```

### Duplicate Check

**Check for duplicates**:
```python
df = pd.read_csv("data/final_output/all_shift_faults.csv")

# Check for duplicates based on log number + timestamp
duplicates = df.duplicated(subset=['ShiftLogNumber', 'timestamp', 'description'], keep=False)
if duplicates.any():
    print(f"Found {duplicates.sum()} duplicate rows")
    print(df[duplicates])
else:
    print("No duplicates found")
```

### Column Integrity Check

**Verify all expected columns present**:
```python
expected_cols = [
    'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
    'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 
    'ShiftHall', 'FragmentLink', 'verification_status'
]

df = pd.read_csv("data/final_output/all_shift_faults.csv")
missing = [col for col in expected_cols if col not in df.columns]

if missing:
    print(f"Missing columns: {missing}")
else:
    print("All expected columns present")
```

---

## Related Documentation

- [Timestamp Fixing](./PIPELINE_FIXING.md) - Previous stage
- [Dashboard](./DASHBOARD.md) - Visualization of final output
- [Output Formats](./OUTPUT_FORMATS.md) - CSV specifications

---

*For dashboard usage, see [DASHBOARD.md](./DASHBOARD.md).*