# Fault Extraction Pipeline

Detailed documentation for the fault extraction stage of CLAW-Agent.

---

## Overview

The fault extraction stage uses LLMs to identify and extract fault information from shift summaries. This is the core intelligence layer that transforms raw text into structured fault records.

**Module**: `src/analysis/shift_summary.py`

**Main Function**: `main_function2(agent: str = None, max_workers: int = 4, batch_size: int = None)`

**Key Parameters**:
- `agent`: openclaw agent name (defaults to `AGENT_NAME` from config)
- `max_workers`: Parallel worker count (default: 4, optimized for benchmark)
- `batch_size`: If set >1, enables batch processing; `None` = single-item parallel processing

**Pipeline Position**: Stage 2 (after data loading, before tagging)

**Input**: Shift summaries DataFrame with columns: `LogNumber`, `DateTime`, `NormalizedContent`/`Content`, `LogbookURL`, `Title`, `Hall`

**Output**: Faults DataFrame with timestamps, descriptions, tags (default "Other"), run numbers, and fragment links

---

## Extraction Process

### LLM Prompt Structure

The extraction prompt instructs the LLM to:

1. Identify faults (errors, crashes, delays, alarms, trips, etc.)
2. Extract exact timestamps in HH:MM format
3. Provide brief descriptions
4. Include run numbers when available (as STRING, e.g., "12345")
5. Return ONLY valid JSON array

**Prompt Template** (single summary):
```
Extract any and all faults (errors, crashes, delays, etc.) from the following shift summary.

Format each fault as a JSON object with these fields:
- timestamp: time in HH:MM 24-hour format (e.g., "20:05") - REQUIRED
- description: brief description of the fault - REQUIRED
- run_number: run number if mentioned - OPTIONAL (omit if not present)

CRITICAL TIMESTAMP RULES:
1. ONLY extract timestamps in the correct format.
2. Acceptable formats: "14:30", "2:30 PM", "1430", "02:30pm"
3. DO NOT create faults if the time is:
   - Vague ("around", "approximately", "before", "after", "during")
   - Relative ("45min into run", "1hr into run", "last 2 hours")
   - Unknown ("N/A", "unspecified", "unknown", "before start")
   - A time range ("17:00-18:20")

IMPORTANT:
- Every fault MUST have timestamp and description fields
- run_number MUST be a STRING (e.g., "12345" not 12345) - wrap in quotes!
- Return ONLY a JSON array of fault objects, nothing else

Example output format:
[
  {"timestamp": "08:15", "description": "RF system trip", "run_number": "12345"},
  {"timestamp": "14:30", "description": "Cooling failure"}
]

Shift Summary:
{shift_summary}
```

### Example Input/Output

**Input (Shift Summary)**:
```
Shift Summary : 04.02.2025 Owl shift

01:23 - Shift started normally
04:00 - RF issues detected in sector 3
06:15 - Beam recovered, run 4346807 started
10:30 - Cooling system trip
14:45 - Normal operations resumed
```

**Output (JSON)**:
```json
[
  {"timestamp": "04:00", "description": "RF issues detected in sector 3", "run_number": null},
  {"timestamp": "10:30", "description": "Cooling system trip", "run_number": null}
]
```

Note: `run_number` field is **omitted entirely** when not mentioned (not set to null). The LLM should only include it when explicitly found in the summary.

---

## Batch Processing

### Why Batch?

**Single Summary Approach**:
- 100 summaries = 100 LLM calls
- Slow, expensive, inconsistent

**Batched Approach**:
- 100 summaries / 5 per batch = 20 LLM calls
- 5x faster, cheaper, more consistent

### Batch Implementation

**Batch Response Format**:
The LLM returns a JSON array where each element has:
- `source_index`: integer matching the summary order (0, 1, 2...)
- `faults`: array of fault objects with `timestamp`, `description`, and optional `run_number`

**Example**:
```json
[
  {"source_index": 0, "faults": [{"timestamp": "08:15", "description": "RF trip", "run_number": "12345"}]},
  {"source_index": 1, "faults": []}
]
```

**Important**: The batch processor iterates through `batch_results` using `local_idx` to match against `batch_rows`, not `source_idx`. The `source_idx` field is validated but the actual row mapping uses the local batch index.

### Parallel Execution

**ThreadPoolExecutor**:
```python
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = []
    for batch in batches:
        future = executor.submit(process_batch, batch, agent)
        futures.append(future)
    
    all_results = [f.result() for f in as_completed(futures)]
```

**Worker Count**:
- Default: 4 workers (optimized for benchmark)
- Adjust via `max_workers` parameter
- More workers = faster but higher memory usage

---

## Timestamp Normalization

### Supported Formats

The extraction stage accepts multiple timestamp formats and normalizes them to HH:MM (24-hour):

| Input Format | Normalized | Example |
|--------------|------------|---------|
| 24-hour | HH:MM | "14:30" → "14:30" |
| 12-hour AM/PM | HH:MM | "2:30 PM" → "14:30" |
| Military (no colon) | HH:MM | "1430" → "14:30" |
| 12-hour no space | HH:MM | "2:30pm" → "14:30" |
| Around Xpm | HH:00 | "around 9PM" → "21:00" |
| Xpm (no colon) | HH:00 | "9pm" → "21:00" |
| Time range | First time | "17:00-18:20" → "17:00" |
| Just hours | HH:00 | "14" → "14:00" |
| 3-digit military | HH:MM | "930" → "09:30" |
| AM/PM with space | HH:MM | "0:30 AM" → "00:30" |
| AM/PM no space | HH:MM | "0:30AM" → "00:30" |

### Normalization Algorithm

The `normalize_timestamp()` function (in `src/utils/text_utils.py`) handles:
- 24-hour format: "14:30" → "14:30"
- 12-hour AM/PM: "2:30 PM" → "14:30"
- Military time: "1430" → "14:30"
- Edge case: 24:00 returns None (special midnight handling)

For formats that `normalize_timestamp()` misses, the `_extract_fallback_timestamp()` function provides additional patterns:
- Time ranges: "17:00-18:20" → "17:00" (extracts first time)
- AM/PM with space: "0:30 AM" → "00:30", "2:30 PM" → "14:30"
- AM/PM without space: "0:30AM" → "00:30", "2:30pm" → "14:30"
- Around Xpm: "around 9PM" → "21:00"
- Simple Xpm: "9pm" → "21:00", "2 am" → "02:00"
- Military without colon: "1412" → "14:12", "1503" → "15:03"
- 3-digit military: "930" → "09:30"
- Just hours: "14" → "14:00"
- Any HH:MM pattern in messy text: extracts first match

**Special 24:00 Handling**: The code explicitly preserves "24:00" timestamps (after checking the raw LLM response) and passes them to `parse_timestamp_to_datetime()` which handles the date rollover to the next day.

### Unparseable Timestamps

**Rejected Patterns**:
- "n/a", "unspecified", "unknown"
- "beginning", "shift start", "end"
- "before start", "last 2 hours"
- "during run", "around 3pm" (without exact time)
- "before 00:37" (ambiguous)

**Handling**:
- Fault is skipped (not included in output)
- Logged as warning
- Better to miss a fault than extract wrong timestamp

---

## JSON Parsing

### Response Format

LLM must return ONLY a JSON array:

```json
[
  {"timestamp": "04:00", "description": "RF issues", "run_number": "4346807"},
  {"timestamp": "10:30", "description": "Cooling trip"}
]
```

### Parsing Logic

The actual implementation uses **multiple fallback strategies**:

1. **Pydantic validation**: First attempts `FaultReport.model_validate_json()` for structured parsing
2. **Standard JSON parse**: Falls back to `json.loads()` and converts run_numbers to strings
3. **Individual fault extraction**: If both fail, tries to extract individual `{...}` blocks and validates each as a `Fault` model

```python
# Simplified parsing flow
json_match = re.search(r'\[.*\]', response, re.DOTALL | re.IGNORECASE)
if json_match:
    json_str = json_match.group(0)
    try:
        return FaultReport.model_validate_json(json_str)  # Pydantic first
    except:
        try:
            faults_list = json.loads(json_str)
            # Convert run_number to string
            for fault in faults_list:
                if "run_number" in fault and fault["run_number"] is not None:
                    fault["run_number"] = str(fault["run_number"])
            return FaultReport(faults=faults_list)
        except:
            # Last resort: extract individual fault objects
            fault_matches = re.findall(r'\{[^{}]*\}', json_str)
            faults = []
            for fm in fault_matches:
                try:
                    fault = Fault.model_validate_json(fm)
                    faults.append(fault)
                except:
                    pass
            return FaultReport(faults=faults)
```

### Error Handling

**Malformed JSON**:
- Log error
- Return empty list for that batch
- Continue with other batches

**Missing Fields**:
- Skip invalid fault objects
- Log warning for each skip

**Invalid Timestamps**:
- Attempt normalization
- Skip if unparseable
- Log for debugging

---

## Link Generation

### Text Fragment URLs

After extraction, each fault gets a clickable link to the exact timestamp in the logbook:

**Function**: `create_text_fragment_link(url, timestamp, separator)`

```python
def create_text_fragment_link(url: str, timestamp: str, separator: str = ".") -> str:
    # URL-encode timestamp for text fragment
    # "14:30" → "14%3A30"
    fragment_text = quote(timestamp, safe='')
    
    # Append text fragment syntax with separator
    new_url = f"{url}#:~:text={fragment_text}{separator}"
    
    return new_url
```

**Example**:
```
Original: https://logbooks.jlab.org/entry/4346807
With fragment: https://logbooks.jlab.org/entry/4346807#:~:text=04%3A00.
```

When clicked, the browser scrolls to the first occurrence of "04:00" in the page.

---

## Output Schema

### Faults DataFrame Columns

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| `timestamp` | str | Normalized time (HH:MM) | LLM extraction + normalization |
| `description` | str | Fault description | LLM extraction |
| `tag` | str | Fault category (default: "Other") | Added later in tagging stage |
| `run_number` | str | Run number (if available) | LLM extraction |
| `ShiftLogNumber` | int | Logbook entry number | Source metadata |
| `ShiftLogbookURL` | str | URL to logbook entry | Source metadata |
| `ShiftTitle` | str | Shift summary title | Source metadata |
| `ShiftDateTime` | str | Summary creation time | Source metadata |
| `ShiftHall` | str | Hall name | Source metadata |
| `FragmentLink` | str | Clickable timestamp link | Generated |
| `FullTimestamp` | datetime | Combined date+time | Computed |

### Data Types

```python
# After extraction
faults_df = pd.DataFrame({
    'timestamp': ['04:00', '10:30'],
    'description': ['RF issues', 'Cooling trip'],
    'tag': ['Other', 'Other'],  # Default; set from LLM if provided, else 'Other'
    'run_number': [None, None],  # String when present, None when omitted
    'ShiftLogNumber': [4346807, 4346807],
    'ShiftLogbookURL': ['https://...', 'https://...'],
    'ShiftTitle': ['Shift Summary...', 'Shift Summary...'],
    'ShiftDateTime': ['2025-04-02 01:23:00', '2025-04-02 01:23:00'],
    'ShiftHall': ['hall_c', 'hall_c'],
    'FragmentLink': ['https://...#:~:text=04%3A00.', ...],
    'FullTimestamp': [datetime(2025, 4, 2, 4, 0), ...]  # Includes 24:00 rollover handling
})
```

**Note on Tags**: Single-row processing preserves any `tag` field from the LLM response (`fault.tag if fault.tag else 'Other'`), while batch processing always sets `'tag': 'Other'` since the batch prompt doesn't ask for tags.

---

## Performance Characteristics

### Time Complexity

**Single Summary**: O(1) LLM call

**Batched**: O(n/b) LLM calls where:
- n = number of summaries
- b = batch size

**Parallel**: O(n/(b*w)) where w = worker count

**Example**:
- 100 summaries, batch=5, workers=5
- Batches: 100/5 = 20 batches
- Parallel: 20/5 = 4 rounds
- Total: 4 LLM call rounds (vs 100 sequential)

### Typical Latencies

| Configuration | Time per 100 summaries |
|---------------|------------------------|
| Sequential, no batch | ~500 seconds |
| Parallel (4 workers), no batch | ~125 seconds |
| Parallel (4 workers), batch=5 | ~30 seconds |

### Token Usage

**Per Summary (no batch)**:
- Input: ~500 tokens (shift summary)
- Output: ~50 tokens (2-3 faults)
- Total: ~550 tokens

**Per Batch (5 summaries)**:
- Input: ~2500 tokens (5 summaries + prompt)
- Output: ~250 tokens (10-15 faults)
- Total: ~2750 tokens

**Cost Estimate** (at $0.001/1K tokens):
- 100 summaries: ~$0.03
- 1000 summaries: ~$0.30

---

## Quality Assurance

### Extraction Accuracy

**What Works Well**:
- Exact timestamps in standard formats
- Clear fault descriptions
- Obvious errors/trips/alarms

**Edge Cases**:
- Vague time references (rejected)
- Multiple faults in one sentence (may merge or split)
- Faults without timestamps (skipped)

### Validation Checks

**Post-Extraction**:
```python
def validate_faults_df(df):
    # Check required columns
    required = ['timestamp', 'description', 'ShiftLogNumber']
    for col in required:
        assert col in df.columns, f"Missing column: {col}"
    
    # Check timestamp format
    assert df['timestamp'].str.match(r'^\d{2}:\d{2}$').all(), "Invalid timestamp format"
    
    # Check no empty descriptions
    assert not df['description'].isnull().any(), "Empty descriptions found"
```

### Common Issues

**Issue**: Timestamps in wrong format
**Fix**: Check `normalize_timestamp()` and `_extract_fallback_timestamp()` logic

**Issue**: Missing faults
**Fix**: Increase batch size, adjust prompt, or check LLM temperature

**Issue**: False positives (non-faults)
**Fix**: Enable `--filter` flag for validation stage

**Issue**: Duplicate faults
**Fix**: Deduplicate after extraction (not automatic in extraction stage)

**Issue**: 24:00 midnight handling  
**Fix**: The code explicitly checks the **raw LLM response** for "24:00" patterns before calling `normalize_timestamp()`. If found, it preserves "24:00" and passes it to `parse_timestamp_to_datetime()` which handles the date rollover to the next day. This avoids losing midnight faults.

---

## Usage Examples

### Basic Extraction

```python
from src.analysis.shift_summary import main_function2

# Run extraction with defaults (no batching, 4 workers, default agent)
faults_df, start_time = main_function2()

print(f"Extracted {len(faults_df)} faults")
print(f"Time range: {faults_df['timestamp'].min()} to {faults_df['timestamp'].max()}")
```

### Custom Configuration

```python
# With custom agent and parallelism
faults_df, start_time = main_function2(
    agent="fault_analyst",
    max_workers=8
)

# With batching enabled
```

### Direct Batch Processing

```python
from src.analysis.shift_summary import extract_faults_batch

batch_data = [
    (0, "4346807", "04:00 - RF issues detected"),
    (1, "4346808", "10:30 - Cooling trip"),
]

results = extract_faults_batch(
    batch_data=batch_data,
    agent="fault_analyst",
    max_workers=2,
    batch_size=2
)

for fault in results:
    print(f"{fault['timestamp']}: {fault['description']}")
```

---

## Testing

### Unit Tests

**Test Timestamp Normalization**:
```python
def test_normalize_timestamp():
    assert normalize_timestamp("14:30") == "14:30"
    assert normalize_timestamp("2:30 PM") == "14:30"
    assert normalize_timestamp("1430") == "14:30"
    assert normalize_timestamp("9pm") == "21:00"
    assert normalize_timestamp("n/a") is None
```

**Test JSON Parsing**:
```python
def test_parse_extraction_response():
    response = '[{"timestamp": "04:00", "description": "Test fault"}]'
    results = parse_extraction_response(response, [])
    
    assert len(results) == 1
    assert results[0]['timestamp'] == "04:00"
    assert results[0]['description'] == "Test fault"
```

### Integration Tests

**Test Full Extraction**:
```python
def test_extraction_integration():
    # Load sample data
    shift_df = pd.read_csv("data/raw/shift_summary.csv")
    
    # Run extraction
    faults_df, _ = main_function2(agent="fault_analyst", max_workers=2, batch_size=2)
    
    # Validate output
    assert faults_df is not None
    assert len(faults_df) > 0
    assert 'timestamp' in faults_df.columns
    assert 'description' in faults_df.columns
```

---

## Troubleshooting

### "No JSON in response"

**Cause**: LLM didn't return valid JSON

**Fix**:
1. Check prompt template clarity
2. Increase temperature for more compliant responses
3. Add retry logic

**Debug**:
```python
# Log full response
logger.debug(f"LLM response: {response}")
```

### "Timestamp normalization failed"

**Cause**: Unrecognized timestamp format

**Fix**:
1. Add format to `normalize_timestamp()`
2. Add fallback in `_extract_fallback_timestamp()`
3. Reject if truly unparseable

**Debug**:
```python
# Log failed timestamps
logger.warning(f"Could not normalize: {raw_timestamp}")
```

### "Too many false positives"

**Cause**: LLM extracting non-faults

**Fix**:
1. Enable `--filter` flag for validation stage
2. Tighten prompt criteria
3. Post-filter with rules

---

## Related Documentation

- [Fault Filtering](./PIPELINE_FAULT_FILTERING.md) - Remove non-faults
- [LLM Utilities](./UTILS_LLM.md) - LLM call implementation
- [Text Utilities](./UTILS_TEXT.md) - Timestamp normalization
- [Architecture](./ARCHITECTURE.md) - Overall pipeline design

---

*For tagging details, see [PIPELINE_TAGGING.md](./PIPELINE_TAGGING.md).*
