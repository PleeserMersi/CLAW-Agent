# Fault Filtering Pipeline

Detailed documentation for the fault validation and filtering stage of CLAW-Agent.

---

## Overview

The filtering stage validates extracted fault descriptions using LLMs to remove non-fault entries (e.g., routine operations, status updates, or false positives from extraction).

**Module**: `src/analysis/fault_filter.py`

**Pipeline Position**: Stage 2 (after extraction, before tagging) (Optional)

**Input**: Extracted faults DataFrame

**Output**: Valid faults DataFrame + Removed faults DataFrame

---

## Filtering Process

### Why Filter?

The fault extraction stage may produce:
- **True faults**: Actual equipment issues or problems
- **False positives**: Routine operations, status updates, or normal events
- **Ambiguous entries**: Unclear if they represent faults

**Example**:
| Description | Classification | Reason |
|-------------|----------------|--------|
| "RF cavity trip at 14:30" | ✅ Fault | Clear equipment failure |
| "Shift started normally" | ❌ Not a fault | Status update |
| "Beam recovered at 15:00" | ❌ Not a fault | Recovery, not fault |
| "Routine maintenance completed" | ❌ Not a fault | Normal operation |

### Validation Prompt

**Prompt Template**:
```
You are a fault validation system. Output ONLY "Yes" or "No".

TASK: Determine if this log entry describes a valid fault/event:
- YES if it describes: fault, error, crash, delay, alarm, trip, reboot, failure, issue, problem, shutdown
- NO if it describes: routine operations, normal status updates, informational notes, trivia, jokes

LOG ENTRY: {description}

OUTPUT:
- "Yes" if it is a valid fault/event
- "No" if it is NOT a fault/event

Output ONLY the word "Yes" or "No". No punctuation, no explanation.
```

### Example Filtering

**Input**:
```
Description: "Shift started normally at 01:00"
```

**LLM Response**: `No`

**Result**: Entry removed from fault list

---

## Batch Processing

### Batch Implementation

**Batch Size**: Configurable via `--filter-size` (default: 10)

**Batch Prompt**:
```
Determine which entries are valid faults. Return ONLY a JSON array.

Each element must have:
- "index": integer matching the fault order below (0, 1, 2...)
- "valid": "Yes" if it is a valid fault, "No" if it is NOT a valid fault

TASK: A valid fault describes: error, crash, delay, alarm, trip, reboot, failure, issue, problem, shutdown
An invalid entry describes: routine operations, normal status updates, informational notes, trivia, jokes

Faults to validate:
{faults_block}
```

**Note**: The `{faults_block}` is formatted as:
```
--- FAULT 0 (original row 42) ---
Description text here

--- FAULT 1 (original row 43) ---
Next description
```

**Expected Response**:
```json
[
  {"index": 0, "valid": "No"},
  {"index": 1, "valid": "Yes"},
  {"index": 2, "valid": "No"}
]
```

---

## Processing Modes

### Single-Item Processing

**Use Case**: Small datasets (< 50 faults)

**Behavior**: Each fault validated individually

**Pros**:
- Simpler error handling
- Better for debugging

**Cons**:
- More LLM calls
- Slower for large datasets

### Batch Processing

**Use Case**: Medium to large datasets (50+ faults)

**Behavior**: Multiple faults validated in single LLM call

**Pros**:
- Fewer LLM calls
- Faster throughput
- Lower token usage

**Cons**:
- More complex parsing
- Single failure affects batch

---

## Parallel Processing

### Worker Configuration

**Default**: 4 parallel workers

**Configuration**: `--workers N`

**Scaling**:
- 4 cores: 4 workers
- 8 cores: 6-8 workers
- 16+ cores: 10-12 workers

### Thread Safety

**Worker Function**: `_validate_single_fault()`

```python
def _validate_single_fault(row: pd.Series, agent: str = None) -> Tuple[str, bool]:
    # Extract data from row
    log_number = str(row.get('ShiftLogNumber', 'Unknown'))
    description = row.get('description', '')
    
    if not description:
        return log_number, True  # Empty description - keep it
    
    # Call LLM
    prompt = PROMPT_TEMPLATES["fault_validation"].format(description=description)
    reply = call_llm(prompt, agent=agent)
    
    # Parse response
    if reply:
        result = reply.strip().lower()
        return log_number, result == "yes"
    
    # Default to True if no response (conservative)
    logger.warning(f"No LLM response for fault validation: {description}")
    return log_number, True
```

### Batch Worker Function

**Function**: `validate_faults_batch()`

```python
def validate_faults_batch(batch_data: List[Tuple[int, int, str]], agent: str = None) -> List[Tuple[int, bool]]:
    # Build batch prompt with local and original indices
    faults_block = ""
    for local_idx, orig_idx, description in batch_data:
        faults_block += f"--- FAULT {local_idx} (original row {orig_idx}) ---\n{description}\n\n"
    
    prompt = PROMPT_TEMPLATES["fault_validation_batch"].format(faults_block=faults_block)
    response = call_llm(prompt, agent=agent)
    
    if not response:
        logger.warning("No response from LLM for batch validation")
        return [(orig_idx, True) for _, orig_idx, _ in batch_data]
    
    # Parse JSON response - extract array from response
    results = {}
    try:
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if not json_match:
            return [(orig_idx, True) for _, orig_idx, _ in batch_data]
        
        batch_data_parsed = json.loads(json_match.group(0))
        local_to_orig = {local_idx: orig_idx for local_idx, orig_idx, _ in batch_data}
        
        for item in batch_data_parsed:
            local_idx = item.get("index")
            valid_str = item.get("valid", "Yes")
            is_valid = valid_str.strip().lower() == "yes"
            
            if local_idx in local_to_orig:
                orig_idx = local_to_orig[local_idx]
                results[orig_idx] = (orig_idx, is_valid)
        
        return [results.get(orig_idx, (orig_idx, True)) for _, orig_idx, _ in batch_data]
    except Exception as e:
        logger.error(f"Failed to parse batch validation response: {e}")
        return [(orig_idx, True) for _, orig_idx, _ in batch_data]
```

---

## Output Files

### Valid Faults

**File**: Not saved separately (returned to pipeline)

**Content**: Faults validated as "Yes"

**Next Step**: Passed to tagging stage

### Removed Faults

**File**: `data/processed/not_faults.csv`

**Content**: Faults validated as "No"

**Schema**: Same as input DataFrame

**Purpose**: Audit trail, debugging, manual review

### Output Example

**not_faults.csv**:
```csv
timestamp,description,tag,ShiftLogNumber,...
01:00,Shift started normally,,4346807,...
15:00,Beam recovered,,4346807,...
```

---

## Error Handling

### No LLM Response

**Symptom**: `call_llm()` returns None

**Handling**: Default to "Yes" (conservative - keep the fault)

**Rationale**: Better to keep a false positive than lose a real fault

**Log**: Warning message

```python
logger.warning(f"No LLM response for fault validation: {description}")
return log_number, True
```

### Invalid LLM Response

**Symptom**: Response not "Yes" or "No"

**Handling**: Parse as lowercase, check for "yes"

**Example**:
- "YES" → True
- "yes" → True
- "No" → False
- "maybe" → False (not "yes")

### Batch Parse Failure

**Symptom**: JSON parsing error

**Handling**: Keep all faults in batch (conservative)

**Log**: Error with full response

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
| Parallel (4 workers), batch=10 | ~2.5 seconds |

### Token Usage

**Per Fault**:
- Input: ~100 tokens (description + prompt)
- Output: ~3 tokens ("Yes" or "No")
- Total: ~103 tokens

**Per Batch (10 faults)**:
- Input: ~1000 tokens
- Output: ~30 tokens
- Total: ~1030 tokens

---

## Usage Examples

### Basic Filtering

```python
from src.analysis.fault_filter import filter_faults

valid_df, removed_df = filter_faults(
    faults_df=faults_df,
    agent="fault_analyst",
    max_workers=4,
    batch_size=None  # No batching
)

print(f"Valid: {len(valid_df)}")
print(f"Removed: {len(removed_df)}")
```

### Batch Filtering

```python
valid_df, removed_df = filter_faults(
    faults_df=faults_df,
    agent="fault_analyst",
    max_workers=4,
    batch_size=10
)
```

### Direct Validation

```python
from src.analysis.fault_filter import is_valid_fault

description = "RF cavity trip at 14:30"
is_fault = is_valid_fault(description, agent="fault_analyst")

print(f"Is fault: {is_fault}")  # True
```

---

## Quality Assurance

### Filter Rate

**Expected**: 5-20% of extracted entries removed as non-faults

**Below 5%**:
- Extraction may be too strict
- LLM may be too lenient

**Above 20%**:
- Extraction may be too aggressive
- Review extraction prompt

### Manual Sampling

**Process**:
1. Sample 20-30 removed faults
2. Manually verify they're not faults
3. Calculate accuracy rate

**Target**: >90% accuracy

---

## Troubleshooting

### "All faults removed"

**Cause**: LLM too strict or prompt issue

**Fix**:
1. Check prompt template
2. Review LLM behavior
3. Test with known faults

**Debug**:
```python
from src.analysis.fault_filter import is_valid_fault

test_faults = [
    "RF cavity trip",
    "Beam loss",
    "Vacuum leak"
]

for desc in test_faults:
    result = is_valid_fault(desc)
    print(f"{desc}: {'Fault' if result else 'Not fault'}")
```

### "No faults removed"

**Cause**: LLM too lenient or extraction already strict

**Fix**:
1. Review extraction prompt
2. Tighten validation prompt
3. Check for extraction issues

### "Batch parsing errors"

**Cause**: LLM not returning valid JSON

**Fix**:
1. Review batch prompt
2. Add more examples
3. Fall back to single-item mode

---

## Related Documentation

- [Fault Extraction](./PIPELINE_FAULT_EXTRACTION.md) - Previous stage
- [Tagging](./PIPELINE_TAGGING.md) - Next stage
- [LLM Utilities](./UTILS_LLM.md) - LLM call implementation
- [Prompt Templates](./CONFIGURATION.md#prompt-templates)

---

*For tagging details, see [PIPELINE_TAGGING.md](./PIPELINE_TAGGING.md).*
