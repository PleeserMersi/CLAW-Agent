# Timestamp Fixing Pipeline

Detailed documentation for the timestamp correction stage of CLAW-Agent.

---

## Overview

The fixing stage corrects inaccurate timestamps by extracting the correct time from full logbook entries. This stage only processes faults marked as "inaccurate" in the verification stage.

**Module**: `src/analysis/fixer.py`

**Pipeline Position**: Stage 4 (after verification)

**Input**: Inaccurate faults DataFrame

**Output**: Fixed faults DataFrame + Manual review DataFrame

---

## Fixing Process

### Why Full Logbook Entries?

Shift summaries are condensed versions. Full logbook entries contain:
- More detailed descriptions
- Exact timestamps in context
- Additional fault information
- Original formatting

**Example**:
- **Summary**: "04:00 - RF issues"
- **Full Entry**: "At 04:00 during run 4346807, we experienced an RF cavity trip in sector 3. The beam was lost for approximately 15 minutes."

### Extraction Prompt

**Prompt Template**:
```
You are a precise data extraction assistant. Return ONLY a timestamp.

CONTEXT:
- Fault description: {description}

FULL LOGBOOK ENTRY (source of truth):
{logbook_content}

TASK:
Extract the CORRECT timestamp for this fault from the logbook.
Output ONLY the timestamp in HH:MM 24-hour format (e.g., "14:30").
No punctuation, no explanation, no extra text.
```

### Example Fixing

**Input**:
```
Fault description: RF issues detected
Incorrect timestamp: 04:15
Full logbook: "At 04:00 during run 4346807, we experienced an RF cavity trip..."
```

**LLM Response**: `04:00`

**Result**: Timestamp corrected from 04:15 to 04:00

---

## 24:00 (Midnight) Handling

### Special Case

**Problem**: Faults occurring at midnight (00:00) may be logged as "24:00" of the previous day.

**Solution**: Return "24:00" from LLM, handle date rollover in code.

**Implementation**:
```python
if corrected_timestamp == "24:00":
    # Parse current FullTimestamp and add one day
    current_dt = datetime.fromisoformat(full_timestamp)
    new_dt = current_dt + timedelta(days=1)
    new_dt = new_dt.replace(hour=0, minute=0)
    
    updated_row['FullTimestamp'] = new_dt
    updated_row['timestamp'] = "00:00"  # Store as 00:00 in CSV
```

### Example

**Original**:
- Date: 2025-04-02
- Time: 24:00 (midnight)

**Fixed**:
- Date: 2025-04-03 (next day)
- Time: 00:00

**Important**: The LLM returns "24:00" for midnight, but the code converts this to "00:00" in the `timestamp` column and adjusts the `FullTimestamp` date by +1 day. You will NOT see "24:00" in the output CSVs.

---

## Re-verification

### Why Re-verify?

After fixing, we verify the correction is accurate:

1. Ensures fix is correct
2. Catches LLM extraction errors
3. High confidence = automatic, low confidence = manual review

### Re-verification Process

```python
def _fix_single_timestamp(row, shift_summaries, agent):
    # Extract correct timestamp
    corrected = extract_correct_timestamp(description, logbook_content, agent)
    
    if corrected:
        # Update row
        updated_row = row.to_dict()
        updated_row['timestamp'] = corrected
        
        # Re-verify against shift summary
        if shift_summary:
            if verify_timestamp_accuracy(updated_row, shift_summary, agent):
                updated_row['fix_confidence'] = 'high'
                return log_number, updated_row, 'fixed'
        
        # If re-verification fails or no summary
        updated_row['fix_confidence'] = 'low'
        return log_number, updated_row, 'low_confidence'
```

---

## Output Files

### Fixed Faults

**File**: `data/fixed/fixed.csv`

**Content**: Successfully corrected timestamps

**Schema**:
| Column | Type | Description |
|--------|------|-------------|
| All fault columns | - | From input DataFrame |
| `fix_confidence` | str | "high" (re-verified) |

### Manual Review

**File**: `data/final_output/manual_check.csv`

**Content**: Low-confidence fixes requiring human review

**Schema**:
| Column | Type | Description |
|--------|------|-------------|
| All fault columns (except fix_confidence, verification_status) | - | From input DataFrame |

### Output Example

**fixed.csv**:
```csv
timestamp,description,tag,ShiftLogNumber,fix_confidence,...
04:00,RF issues detected,Accelerator,4346807,high,...
10:30,Cooling trip,Mechanical,4346807,high,...
```

**manual_check.csv**:
```csv
timestamp,description,tag,ShiftLogNumber,FullTimestamp,...
04:15,Unclear fault,Other,4347000,2025-04-02T04:15:00,...
```

**Note**: `manual_check.csv` does NOT include `fix_confidence` or `verification_status` columns - these are stripped to keep the file clean for manual review.

---

## Batch Processing

### Batch Implementation

**Batch Size**: Configurable via `--fixing-size` (default: 10)

**Batch Prompt**:
```
Extract the correct timestamp for each fault from the logbook entry. Return ONLY a JSON array.

Each element must have:
- "index": integer matching the fault order below (0, 1, 2...)
- "timestamp": the correct time in HH:MM format, or "24:00" for midnight

TASK: Find the exact time mentioned in the logbook that matches each fault description.
- Look for time patterns like "14:30", "2:30 PM", "1430", "2:30"
- If the fault occurred at midnight, return "24:00" (caller will handle date rollover)
- If you cannot find a matching timestamp, return ""

Logbook Entry:
{logbook_content}

Faults to fix:
--- FAULT 0 (original row 15, Log 4346807) ---
Description: RF issues detected

--- FAULT 1 (original row 23, Log 4346807) ---
Description: Cooling system trip

--- FAULT 2 (original row 31, Log 4346807) ---
Description: Beam loss
...
```

**Expected Response**:
```json
[
  {"index": 0, "timestamp": "04:00"},
  {"index": 1, "timestamp": "10:30"},
  {"index": 2, "timestamp": "24:00"}
]
```

**Note**: The actual batch prompt includes additional metadata (original row index and log number) for each fault to help with debugging and traceability.

---

## API Integration

### Fetching Logbook Entries

**Function**: `get_logbook_entry_by_log_number()`

```python
def get_logbook_entry_by_log_number(log_number: str) -> Optional[str]:
    api_client = CachedAPIClient(
        base_url=JLAB_LOGBOOK_BASE_URL,
        username=JLAB_USERNAME,
        password=JLAB_PASSWORD
    )
    
    entry = api_client.get_single_entry(log_number)
    
    if not entry:
        return None
    
    # Extract body content
    data = entry.get('data', {})
    entry_data = data.get('entry', {})
    body = entry_data.get('body', {})
    content = body.get('content', '')
    
    return content
```

### Caching

**Benefit**: Same logbook entry may be fetched multiple times

**Cache TTL**: 30 minutes

**Cache Key**: Log number

---

## Confidence Levels

### High Confidence

**Criteria**:
- Timestamp extracted successfully
- Re-verification passed (within 15 min of summary)
- No ambiguity

**Action**: Include in `fixed.csv`, proceed to consolidation

### Low Confidence

**Criteria**:
- Timestamp extracted but re-verification failed
- No shift summary available for comparison
- Ambiguous extraction

**Action**: Include in `manual_check.csv` for human review

---

## Performance

### Time Complexity

**Per Fault**:
- API fetch: O(1) (cached)
- LLM extraction: O(1)
- Re-verification: O(1)

**Batched**: O(n/b) LLM calls

**Parallel**: O(n/(b*w)) with w workers

### Typical Latencies

| Configuration | Time per 100 faults |
|---------------|---------------------|
| Sequential, batch=1 | ~150 seconds |
| Sequential, batch=10 | ~15 seconds |
| Parallel (5 workers), batch=10 | ~3 seconds |

### Token Usage

**Per Fault **(single mode)
- Input: ~1500 tokens (logbook content)
- Output: ~5 tokens (timestamp)
- Total: ~1505 tokens

**Per Batch **(10 faults, batched mode)
- Input: ~1500 tokens (shared logbook + fault descriptions)
- Output: ~50 tokens (JSON array)
- Total: ~1550 tokens

**Batched mode re-verification**:
- Also batches the re-verification step using `verify_timestamps_batch()`
- Further reduces LLM calls by grouping verification checks

---

## Usage Examples

### Basic Fixing

```python
from src.analysis.fixer import fix_timestamps

fixed_df, manual_df = fix_timestamps(
    agent="fault_analyst",
    max_workers=5,
    batch_size=10
)

print(f"Fixed: {len(fixed_df)}")
print(f"Manual review: {len(manual_df)}")
```

### Direct Extraction

```python
from src.analysis.fixer import extract_correct_timestamp

fault_desc = "RF issues detected"
logbook = "At 04:00 during run 4346807, we experienced an RF cavity trip..."

corrected = extract_correct_timestamp(fault_desc, logbook, agent="fault_analyst")
print(f"Corrected timestamp: {corrected}")  # "04:00"
```

### Single Fault Fix

```python
from src.analysis.fixer import _fix_single_timestamp

row = faults_df.iloc[0]
shift_summaries = {"4346807": "04:00 - RF issues"}

log_num, updated_row, status = _fix_single_timestamp(row, shift_summaries, agent="fault_analyst")
print(f"Status: {status}")  # "fixed" or "low_confidence"
print(f"New timestamp: {updated_row['timestamp']}")
```

---

## Quality Assurance

### Fix Success Rate

**Expected**: 60-80% of inaccurate faults can be fixed

**Below 60%**:
- Logbook entries may be missing
- LLM extraction failing
- Check API connectivity

**Above 90%**:
- Excellent extraction performance
- May indicate verification is too strict

### Manual Review Rate

**Expected**: 10-30% of fixes require manual review

**High manual review**:
- Check re-verification threshold
- Review low-confidence cases
- Adjust prompt for better extraction

---

## Troubleshooting

### "Could not fetch logbook"

**Cause**: API call failed or entry doesn't exist

**Fix**:
1. Check API credentials
2. Verify log number format
3. Test API manually

**Debug**:
```python
from src.analysis.fixer import get_logbook_entry_by_log_number

content = get_logbook_entry_by_log_number("4346807")
print(f"Content length: {len(content) if content else 0}")
```

### "No timestamp extracted"

**Cause**: LLM couldn't find timestamp in logbook

**Fix**:
1. Check logbook content quality
2. Review prompt clarity
3. May need manual review

**Debug**:
```python
# Log the extraction attempt
logger.debug(f"Logbook snippet: {logbook_content[:500]}")
logger.debug(f"LLM response: {response}")
```

### "Batch parsing failed"

**Cause**: LLM response doesn't contain valid JSON array

**Fix**:
1. Check LLM response format in logs
2. May indicate model confusion - try smaller batches
3. Check for rate limiting or timeout issues

**Debug**:
```python
# The code logs the full response on parse failure
logger.warning(f"Full response: {response}")
```

### "Re-verification failed"

**Cause**: Fixed timestamp still doesn't match summary

**Fix**:
1. Check shift summary accuracy
2. Review tolerance threshold
3. Flag for manual review

---

## Related Documentation

- [Timestamp Verification](./PIPELINE_VERIFICATION.md) - Previous stage
- [Consolidation](./PIPELINE_CONSOLIDATION.md) - Next stage
- [Caching](./UTILS_CACHE.md) - API caching details
- [LLM Utilities](./UTILS_LLM.md) - LLM call implementation

---

*For consolidation details, see [PIPELINE_CONSOLIDATION.md](./PIPELINE_CONSOLIDATION.md).*