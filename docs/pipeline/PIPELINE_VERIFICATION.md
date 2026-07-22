# Timestamp Verification Pipeline

Detailed documentation for the timestamp verification stage of CLAW-Agent.

---

## Overview

The verification stage uses LLMs to validate that extracted fault timestamps match the source shift summaries. Faults with inaccurate timestamps are separated for correction.

**Module**: `src/analysis/accuracy_test.py`

**Pipeline Position**: Stage 3 (after tagging)

**Input**: Faults DataFrame with timestamps

**Output**: Two DataFrames - accurate faults and inaccurate faults

---

## Verification Process

### LLM Verification Prompt

The verification prompt asks the LLM to determine if a timestamp is accurate based on:

1. Timestamp exists in the fault information
2. Timestamp is within 15 minutes of the time in the shift summary

**Prompt Template**:
```
You are a fault verification system. Output ONLY "Yes" or "No".

FAULT TIMESTAMP TO VERIFY:
{timestamp_info}

FULL SHIFT SUMMARY (source of truth):
{full_summary}

VERIFICATION RULES (ALL must pass for "Yes"):
1. Timestamp EXISTS in fault information (missing = "No")
2. Timestamp is within 15 minutes of time in shift summary

OUTPUT:
- "Yes" = all rules passed
- "No" = one or more rules failed

Output ONLY the word "Yes" or "No". No punctuation, no explanation.
```

### Example Verification

**Input**:
```
FAULT TIMESTAMP TO VERIFY:
04:00 - RF issues detected

FULL SHIFT SUMMARY (source of truth):
Shift Summary : 04.02.2025 Owl shift

01:23 - Shift started normally
04:00 - RF issues detected in sector 3
06:15 - Beam recovered
```

**LLM Response**: `Yes`

---

## Tolerance Threshold

### 15-Minute Window

**Configuration**: `TIMESTAMP_TOLERANCE_MINUTES = 15`

**Rationale**:
- Shift summaries may not list exact minute
- LLM extraction may have slight variance
- Allows for reasonable interpretation

**Examples**:
| Extracted | Actual in Summary | Within Tolerance? |
|-----------|-------------------|-------------------|
| 04:00 | 04:00 | ✅ Yes |
| 04:05 | 04:00 | ✅ Yes (5 min) |
| 04:10 | 04:00 | ✅ Yes (10 min) |
| 04:15 | 04:00 | ✅ Yes (15 min) |
| 04:16 | 04:00 | ❌ No (16 min) |
| 03:45 | 04:00 | ✅ Yes (15 min) |
| 03:44 | 04:00 | ❌ No (16 min) |

---

## Batch Processing

### Batch Implementation

**Batch Size**: Configurable via `batch_size` parameter (default: None = no batching)

**Batch Prompt Template**:
The actual prompt used by `PROMPT_TEMPLATES["timestamp_verification_batch"]`:

```
Determine if these timestamps are accurate. Return ONLY a JSON array.

Each element must have:
- "index": integer matching the fault order below (0, 1, 2...)
- "accurate": "Yes" if the timestamp matches the shift summary, "No" if it does not

TASK: Check if the timestamp and description match something in the shift summary.
- YES if the timestamp and description appear in the summary
- NO if the timestamp is wrong, the description doesn't match, or the fault isn't in the summary

Shift Summary:
{full_summary}

Faults to verify:
{faults_block}
```

Where `{faults_block}` is formatted as:
```
--- FAULT 0 (original row 5, Log 4346807) ---
Timestamp: 04:00
Description: RF issues detected

--- FAULT 1 (original row 8, Log 4346807) ---
Timestamp: 10:30
Description: Cooling system trip
```

**Expected Response**:
```json
[
  {"index": 0, "accurate": "Yes"},
  {"index": 1, "accurate": "No"}
]
```

### Batch Processing Strategy

The implementation uses a two-level batching strategy for efficiency:

1. **Group by shift**: Faults from the same shift log number are grouped together
2. **Chunk into batches**: Each group is split into chunks of `batch_size`

This maximizes efficiency by sharing the shift summary across multiple faults in a single LLM call.

**Batch data structure**:
```python
# Each tuple: (local_idx, orig_idx, timestamp, description, log_number)
batch_data = [
    (0, 5, "04:00", "RF issues detected", "4346807"),
    (1, 8, "10:30", "Cooling system trip", "4346807"),
]
```

**Key implementation details**:
- Shift summaries are pre-loaded into a dictionary for fast lookup
- Each batch is submitted as a single LLM call via `verify_timestamps_batch()`
- Results are mapped back to original DataFrame row indices
- Parallel workers process different batches simultaneously via `ThreadPoolExecutor`

---

## Data Flow

### Step-by-Step Process

```
Faults DataFrame (with timestamps)
       │
       ▼
┌─────────────────────┐
│ Load Shift Summaries│
│ (by log number)     │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Match faults to     │
│ summaries           │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Batch by            │
│ validation_size     │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ LLM Verification    │
│ (Yes/No per fault)  │
└─────────────────────┘
       │
       ▼
┌─────────────────────┐
│ Parse results       │
└─────────────────────┘
       │
       ├───▶ Accurate Faults (saved to accurate.csv)
       └───▶ Inaccurate Faults (saved to inaccurate.csv)
```

---

## Output Files

### Accurate Faults

**File**: `data/verified/accurate.csv`

**Content**: Faults with verified timestamps

**Schema**:
| Column | Type | Description |
|--------|------|-------------|
| All fault columns | - | From input DataFrame |
| (no additional) | - | - |

### Inaccurate Faults

**File**: `data/verified/inaccurate.csv`

**Content**: Faults with incorrect timestamps (need fixing)

**Schema**:
| Column | Type | Description |
|--------|------|-------------|
| All fault columns | - | From input DataFrame |
| (no additional) | - | - |

### Output Example

**accurate.csv**:
```csv
timestamp,description,tag,ShiftLogNumber,...
04:00,RF issues detected,Accelerator,4346807,...
10:30,Cooling system trip,Mechanical,4346807,...
```

**inaccurate.csv**:
```csv
timestamp,description,tag,ShiftLogNumber,...
04:15,RF issues detected,Accelerator,4346807,...
```

---

## Error Handling

### Missing Shift Summary

**Symptom**: Cannot verify fault (no source to compare)

**Handling**:
The `get_shift_summary_by_log_number()` function:
- Looks up the shift summary by LogNumber (converted to string for safe comparison)
- Returns `NormalizedContent` if available, otherwise falls back to `Content`
- Logs a warning and returns `None` if not found

**Result**: Faults without matching shift summaries are **skipped entirely** - they don't appear in either accurate or inaccurate output files.

### LLM Response Errors

**Symptom**: No response or invalid format

**Single-fault verification**:
- No response or invalid response → marked as **inaccurate** (conservative)

**Batch verification**:
- No response → all faults in batch marked as **inaccurate**
- Invalid JSON → all faults in batch marked as **inaccurate**  
- Parse error → logged and all faults in batch marked as **inaccurate**

**Rationale**: Conservative approach ensures potentially incorrect timestamps go to manual review rather than being accepted as accurate.

---

## Performance

### Time Complexity

**Per Fault**: O(1) LLM call

**Batched**: O(n/b) LLM calls where n = faults, b = batch size

**Parallel**: O(n/(b*w)) with w workers

### Typical Latencies

| Configuration | Time per 100 faults |
|---------------|---------------------|
| Sequential, batch=1 | ~100 seconds |
| Sequential, batch=10 | ~10 seconds |
| Parallel (5 workers), batch=10 | ~2 seconds |

### Token Usage

**Per Fault**:
- Input: ~800 tokens (summary + timestamp info)
- Output: ~3 tokens ("Yes" or "No")
- Total: ~803 tokens

**Per Batch (10 faults)**:
- Input: ~8000 tokens (shared summary)
- Output: ~30 tokens
- Total: ~8030 tokens

---

## Usage Examples

### Basic Verification

```python
from src.analysis.accuracy_test import verify_faults

accurate_df, inaccurate_df = verify_faults(
    agent="fault_analyst",
    max_workers=5,
    batch_size=10
)

print(f"Accurate: {len(accurate_df)}")
print(f"Inaccurate: {len(inaccurate_df)}")
```

### Direct Verification

```python
from src.analysis.accuracy_test import verify_timestamp_accuracy

fault_row = {
    'timestamp': '04:00',
    'description': 'RF issues detected'
}

shift_summary = "04:00 - RF issues detected in sector 3"

is_accurate = verify_timestamp_accuracy(fault_row, shift_summary, agent="fault_analyst")
print(f"Accurate: {is_accurate}")  # True
```

### Single Batch Verification

```python
from src.analysis.accuracy_test import verify_timestamps_batch

batch_data = [
    (0, 0, "04:00", "RF issues", "04:00 - RF issues detected"),
    (1, 1, "10:30", "Cooling trip", "10:30 - Cooling system trip"),
]

results = verify_timestamps_batch(batch_data, summary=shift_summary, agent="fault_analyst")

for orig_idx, is_accurate in results:
    print(f"Fault {orig_idx}: {'Accurate' if is_accurate else 'Inaccurate'}")
```

---

## Quality Assurance

### Accuracy Rate

**Expected**: 70-90% of faults accurate on first pass

**Below 70%**:
- Check extraction prompt (too aggressive?)
- Check timestamp normalization
- Review LLM behavior

**Above 95%**:
- May be too lenient (increase strictness)
- Or extraction is very accurate

### Manual Sampling

**Process**:
1. Randomly sample 50 accurate faults
2. Manually verify timestamps
3. Calculate true accuracy rate

**Target**: >90% true accuracy

---

## Troubleshooting

### "No shift summary found"

**Cause**: Log number doesn't match any summary

**Fix**:
1. Check log number format (string vs int)
2. Verify data loading stage completed
3. Check for data corruption

**Debug**:
```python
from src.analysis.accuracy_test import load_shift_summaries

shift_df = load_shift_summaries()
print(f"Loaded {len(shift_df)} summaries")
print(f"Sample log numbers: {shift_df['LogNumber'].head()}")
```

### "All faults marked inaccurate"

**Cause**: LLM too strict or summary mismatch

**Fix**:
1. Check prompt template
2. Verify summary content matches extraction source
3. Adjust tolerance (requires code change)

**Debug**:
```python
# Test single verification
fault = faults_df.iloc[0]
summary = get_shift_summary_by_log_number(str(fault['ShiftLogNumber']))

print(f"Fault: {fault['timestamp']} - {fault['description']}")
print(f"Summary snippet: {summary[:200]}")
```

### "High false positive rate"

**Cause**: LLM marking wrong timestamps as accurate

**Fix**:
1. Tighten prompt rules
2. Reduce tolerance threshold
3. Add more verification criteria

---

## Related Documentation

- [Timestamp Fixing](./PIPELINE_FIXING.md) - Next stage for inaccurate faults  
- [Fault Extraction](./PIPELINE_FAULT_EXTRACTION.md) - Previous stage  
- [LLM Utilities](../../utils/UTILS_LLM.md) - LLM call implementation  
- [Configuration](../../config.py) - Tolerance threshold and paths  

## Implementation Notes

**Key functions in `src/analysis/accuracy_test.py`**:
- `verify_faults()` - Main entry point, handles both single and batch modes
- `verify_timestamps_batch()` - Batch verification with JSON parsing
- `_verify_single_fault()` - Single fault verification worker function
- `get_shift_summary_by_log_number()` - Shift summary lookup by log number
- `load_shift_summaries()` - Load shift summaries CSV into DataFrame

**Configuration** (from `config.py`):
- `TIMESTAMP_TOLERANCE_MINUTES = 15` - Tolerance window for timestamp matching
- `ACCURATE_CSV = data/verified/accurate.csv` - Output for verified accurate faults
- `INACCURATE_CSV = data/verified/inaccurate.csv` - Output for inaccurate faults
- `AGENT_NAME` - OpenClaw agent to use for LLM calls

**Parameters**:
- `batch_size` - Number of faults per batch (None = no batching, single-fault mode)
- `max_workers` - Number of parallel ThreadPoolExecutor workers (default: 4)
- `agent` - OpenClaw agent name (defaults to `AGENT_NAME` from config)