# Text Processing Utilities

Documentation for text processing utilities in CLAW-Agent.

---

## Overview

The text utilities module provides functions for HTML cleaning, timestamp parsing, and text normalization.

**Module**: `src/utils/text_utils.py`

---

## Functions

### `html_to_text(html_content: str) -> str`

Convert HTML content to plain text.

**Parameters**:
- `html_content`: HTML string

**Returns**: Plain text extracted from HTML

**Example**:
```python
html = "<p>Shift started at <strong>14:30</strong></p>"
text = html_to_text(html)
print(text)  # "Shift started at 14:30"
```

**Behavior**:
- Uses BeautifulSoup with `html.parser`
- Removes `<script>` and `<style>` tags via `decompose()`
- Extracts visible text with space separator
- Normalizes all whitespace to single spaces

---

### `clean_text(text: str) -> str`

Clean plain text by normalizing whitespace.

**Parameters**:
- `text`: Input text

**Returns**: Cleaned text

**Example**:
```python
text = "Shift   started    at   14:30"
clean = clean_text(text)
print(clean)  # "Shift started at 14:30"
```

**Behavior**:
- Replaces multiple spaces with single space
- Strips leading/trailing whitespace

---

### `normalize_shift_title(title: str) -> str`

Normalize shift summary title.

**Parameters**:
- `title`: Original title

**Returns**: Normalized title

**Example**:
```python
title = "Shift Summary: 04.02.2025 Owl shift"
normalized = normalize_shift_title(title)
print(normalized)  # "04.02.2025 Owl shift"
```

**Behavior**:
- Removes "Shift Summary:" prefix
- Removes "Hall B Shift Summary:" prefix
- Strips whitespace

---

### `normalize_timestamp(timestamp: str) -> Optional[str]`

Normalize timestamp to HH:MM 24-hour format using regex-based parsing.

**Parameters**:
- `timestamp`: Raw timestamp string

**Returns**: Normalized timestamp in HH:MM format, or `None` if invalid or "24:00"

**Supported Formats**:
| Input | Output | Notes |
|-------|--------|-------|
| "14:30" | "14:30" | Already 24-hour |
| "2:30 PM" | "14:30" | 12-hour with space |
| "2:30pm" | "14:30" | 12-hour no space |
| "02:30 PM" | "14:30" | Zero-padded |
| "12:00 AM" | "00:00" | Midnight |
| "12:00 PM" | "12:00" | Noon |
| "24:00" | `None` | Special case - day rollover needed |
| "invalid" | `None` | Unparseable |

**Implementation Details**:
1. Strips and removes non-time characters (keeps digits, colons, spaces, am/pm)
2. Checks for 24-hour format first (`HH:MM`)
3. Falls back to 12-hour format with am/pm detection
4. Returns `None` for "24:00" to signal date rollover
5. Returns `None` for invalid hour/minute values

**Example**:
```python
ts = normalize_timestamp("2:30 PM")
print(ts)  # "14:30"

ts = normalize_timestamp("24:00")
print(ts)  # None (caller handles date rollover)

ts = normalize_timestamp("invalid")
print(ts)  # None
```

**Special Case**: Returns `None` for "24:00" - caller must handle date rollover (see `parse_timestamp_to_datetime`)

---

### `parse_timestamp_to_datetime(date_str: str, time_str: str) -> Optional[datetime]`

Parse date and time strings into a datetime object.

**Parameters**:
- `date_str`: Date in YYYY-MM-DD format
- `time_str`: Time in HH:MM format (can be "24:00")

**Returns**: datetime object or `None` if parsing fails

**Implementation Details**:
1. Parses date using `datetime.strptime` with `%Y-%m-%d`
2. Checks if time is "24:00" - if so, increments date by 1 day and sets time to 00:00
3. Otherwise parses time using `%H:%M` and replaces hour/minute on date object
4. Returns `None` on any `ValueError`

**Example**:
```python
dt = parse_timestamp_to_datetime("2025-04-02", "14:30")
print(dt)  # 2025-04-02 14:30:00

dt = parse_timestamp_to_datetime("2025-04-02", "24:00")
print(dt)  # 2025-04-03 00:00:00 (date incremented)

dt = parse_timestamp_to_datetime("2025-04-02", "invalid")
print(dt)  # None
```

**Special Case**: Handles "24:00" by incrementing date by one day and setting time to 00:00

---

### `extract_time_from_text(text: str) -> Optional[str]`

Extract a time reference from text using regex patterns.

**Parameters**:
- `text`: Text to search

**Returns**: Extracted time in HH:MM format (24-hour), or `None` if no match

**Implementation Details**:
1. Iterates through patterns in order:
   - Pattern 1: `HH:MM` or `H:MM AM/PM` (e.g., "14:30", "2:30 pm")
   - Pattern 2: `H AM/PM` without minutes (e.g., "2pm", "2 pm")
2. Returns first match found
3. Converts 12-hour to 24-hour format
4. For 24-hour input, returns as-is

**Supported Patterns**:
| Pattern | Example Input | Output |
|---------|--------------|--------|
| `HH:MM` | "14:30" | "14:30" |
| `H:MM AM/PM` | "2:30 PM" | "14:30" |
| `H:MMam/pm` | "2:30pm" | "14:30" |
| `H AM/PM` | "2pm" | "14:00" |
| `H am/pm` | "2 am" | "02:00" |

**Example**:
```python
text = "At 2:30 PM we had an issue"
time = extract_time_from_text(text)
print(time)  # "14:30"

text = "Issue at 14:30"
time = extract_time_from_text(text)
print(time)  # "14:30"

text = "Multiple: 10:00 and 2:00 PM"
time = extract_time_from_text(text)
print(time)  # "10:00" (first match)
```

---

## Timestamp Handling

### 24:00 (Midnight) Special Case

**Problem**: Faults at midnight may be logged as "24:00" of the previous day.

**Solution**:
1. `normalize_timestamp()` returns `None` for "24:00"
2. Caller checks for `None` and handles date rollover
3. `parse_timestamp_to_datetime()` increments date for "24:00"

**Example**:
```python
# In fixer.py
if corrected_timestamp == "24:00":
    # Increment date by one day
    current_dt = datetime.fromisoformat(full_timestamp)
    new_dt = current_dt + timedelta(days=1)
    new_dt = new_dt.replace(hour=0, minute=0)
```

---

## Usage Examples

### HTML Cleaning

```python
from utils.text_utils import html_to_text, clean_text

html = """
<div>
  <p>Shift started normally</p>
  <p>At <strong>14:30</strong>, RF issues detected</p>
  <script>console.log("ignore");</script>
</div>
"""

text = html_to_text(html)
clean = clean_text(text)
print(clean)
# "Shift started normally At 14:30, RF issues detected"
```

### Timestamp Normalization

```python
from utils.text_utils import normalize_timestamp

timestamps = ["14:30", "2:30 PM", "12:00 AM", "24:00"]

for ts in timestamps:
    normalized = normalize_timestamp(ts)
    print(f"{ts} -> {normalized}")

# Output:
# 14:30 -> 14:30
# 2:30 PM -> 14:30
# 12:00 AM -> 00:00
# 24:00 -> None
```

### Date-Time Parsing

```python
from utils.text_utils import parse_timestamp_to_datetime

dt = parse_timestamp_to_datetime("2025-04-02", "14:30")
print(dt)  # 2025-04-02 14:30:00

dt = parse_timestamp_to_datetime("2025-04-02", "24:00")
print(dt)  # 2025-04-03 00:00:00
```

### Time Extraction

```python
from utils.text_utils import extract_time_from_text

texts = [
    "At 2:30 PM we had an issue",
    "Issue at 14:30",
    "No time here",
    "Multiple: 10:00 and 2:00 PM"
]

for text in texts:
    time = extract_time_from_text(text)
    print(f"{text} -> {time}")

# Output:
# At 2:30 PM we had an issue -> 14:30
# Issue at 14:30 -> 14:30
# No time here -> None
# Multiple: 10:00 and 2:00 PM -> 10:00 (first match)
```

---

## Performance

### Time Complexity

| Function | Complexity |
|----------|------------|
| `html_to_text` | O(n) where n = HTML length |
| `clean_text` | O(n) where n = text length |
| `normalize_timestamp` | O(1) (regex match) |
| `parse_timestamp_to_datetime` | O(1) (parsing) |
| `extract_time_from_text` | O(n) where n = text length |

### Typical Latencies

| Function | Time |
|----------|------|
| `html_to_text` (1KB) | ~1 ms |
| `clean_text` (1KB) | <1 ms |
| `normalize_timestamp` | <1 ms |
| `parse_timestamp_to_datetime` | <1 ms |
| `extract_time_from_text` (100 chars) | <1 ms |

---

## Error Handling

### Invalid Timestamp

**Symptom**: `normalize_timestamp()` returns `None`

**Handling**: Caller should handle `None` case

**Example**:
```python
ts = normalize_timestamp("invalid")
if ts is None:
    logger.warning(f"Invalid timestamp: {timestamp}")
```

### HTML Parsing Error

**Symptom**: BeautifulSoup exception

**Handling**: Return empty string or original text

**Current**: No error handling - let exception propagate

---

## Related Documentation

- [Data Loading](./PIPELINE_DATA_LOADING.md) - HTML cleaning usage
- [Fault Extraction](./PIPELINE_FAULT_EXTRACTION.md) - Timestamp parsing
- [Timestamp Fixing](./PIPELINE_FIXING.md) - 24:00 handling

---

*For timestamp fixing details, see [PIPELINE_FIXING.md](./PIPELINE_FIXING.md).*