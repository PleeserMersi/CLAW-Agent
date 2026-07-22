# Link Utilities

Documentation for URL fragment link generation in CLAW-Agent.

---

## Overview

The link utilities module creates **clickable Text Fragment links** that allow users to jump directly to specific timestamps within JLab logbook entries. This enhances the user experience by providing one-click navigation to the exact location of a fault in the original shift summary.

**Module**: `src/analysis/link_logic.py`

**Key Features**:
- Generates Text Fragment URLs following the [web.dev/text-fragment/](https://web.dev/text-fragment/) spec
- Automatic URL encoding for special characters (colons, spaces, etc.)
- Graceful fallback to original URL on errors
- Two link styles: simple timestamp and timestamp with context

---

## Background: Text Fragments

### What Are Text Fragments?

**Text Fragments** (also called "Text Direct Links") are a web standard that enables linking to specific text content within a webpage. When clicked, the browser:

1. Scrolls to the first occurrence of the specified text
2. Highlights the text visually
3. Optionally shows surrounding context

**Syntax**:
```
https://example.com/page#:~:text=fragment
```

**Fragment Formats**:
| Format | Example | Description |
|--------|---------|-------------|
| Simple text | `#:~:text=hello` | Link to first "hello" |
| Start text | `#:~:text=startText` | Link to text starting with "startText" |
| Start-End text | `#:~:text=startText,-,endText` | Link to range from start to end |
| Text with prefix/suffix | `#:~:text=prefix-,target,suffix` | Link to "target" with context |

**Browser Support** (as of 2026):
- ✅ Chrome 80+
- ✅ Edge 80+
- ✅ Opera 67+
- ❌ Firefox (not yet supported)
- ❌ Safari (not yet supported)

**Example**:
```
https://logbooks.jlab.org/entry/4346807#:~:text=14%3A30
```

When clicked in Chrome/Edge:
- Page scrolls to line containing "14:30"
- Text is highlighted with a yellow background
- User sees the exact timestamp location instantly

### Why Use Text Fragments?

**Before**: User clicks link → sees full entry → manually searches for timestamp

**After**: User clicks link → page scrolls directly to timestamp → highlighted

**Benefits**:
- Faster fault verification
- Better user experience
- Reduced scroll time
- Clear visual context

---

## Functions

### `create_text_fragment_link(url: str, timestamp: str, separator: str = ".") -> str`

Creates a simple Text Fragment link that jumps directly to a timestamp.

**Signature**:
```python
def create_text_fragment_link(url: str, timestamp: str, separator: str = ".") -> str
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | Required | Base URL to logbook entry (e.g., `https://logbooks.jlab.org/entry/4346807`) |
| `timestamp` | str | Required | Timestamp to link to (e.g., `"14:30"`, `"08:15"`) |
| `separator` | str | `"."` | Unused in current implementation (reserved for future) |

**Returns**: URL with Text Fragment appended, or original URL on error

**Implementation Details**:

1. **Validation**: Returns original URL if `url` or `timestamp` is empty/None
2. **URL Parsing**: Uses `urlparse()` to decompose URL
3. **URL Encoding**: Uses `quote(timestamp, safe='')` to encode special characters
   - `"14:30"` → `"14%3A30"`
   - `"08:15:30"` → `"08%3A15%3A30"`
4. **Fragment Construction**: Appends `#:~:text={encoded_timestamp}`
5. **Error Handling**: Catches all exceptions, returns original URL unchanged

**Examples**:

```python
from src.analysis.link_logic import create_text_fragment_link

# Basic usage
url = "https://logbooks.jlab.org/entry/4346807"
timestamp = "14:30"

link = create_text_fragment_link(url, timestamp)
print(link)
# https://logbooks.jlab.org/entry/4346807#:~:text=14%3A30

# Timestamp with seconds
timestamp = "08:15:30"
link = create_text_fragment_link(url, timestamp)
print(link)
# https://logbooks.jlab.org/entry/4346807#:~:text=08%3A15%3A30

# Empty timestamp → returns original URL
link = create_text_fragment_link(url, "")
print(link)
# https://logbooks.jlab.org/entry/4346807

# Invalid URL → returns original URL
link = create_text_fragment_link("not-a-url", "14:30")
print(link)
# not-a-url
```

**URL Encoding Behavior**:

| Input | Encoded |
|-------|---------|
| `14:30` | `14%3A30` |
| `08:15:30` | `08%3A15%3A30` |
| `Shift 1` | `Shift%201` |
| `Error#1` | `Error%231` |

**Note**: `safe=''` means ALL special characters are encoded (no characters are "safe")

---

### `create_fragment_link_with_context(url: str, timestamp: str, context_lines: int = 2) -> str`

Creates a Text Fragment link with surrounding context text (prefix and suffix).

**Signature**:
```python
def create_fragment_link_with_context(url: str, timestamp: str, context_lines: int = 2) -> str
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | Required | Base URL to logbook entry |
| `timestamp` | str | Required | Timestamp to link to |
| `context_lines` | int | 2 | Unused in current implementation (reserved for future) |

**Returns**: URL with Text Fragment including prefix/suffix context

**Implementation Details**:

1. **Validation**: Returns original URL if `url` or `timestamp` is empty/None
2. **Context Construction**: Uses hardcoded prefix ("Shift") and suffix ("Fault")
3. **URL Encoding**: Encodes all three parts separately
   - Prefix: `quote("Shift", safe='')` → `"Shift"`
   - Timestamp: `quote(timestamp, safe='')` → `"14%3A30"`
   - Suffix: `quote("Fault", safe='')` → `"Fault"`
4. **Fragment Format**: `{prefix}-,*{timestamp}*,{suffix}`
   - `-` separates prefix from target
   - `*` indicates exact match for timestamp
   - `,` separates target from suffix
5. **Error Handling**: Returns original URL on any exception

**Examples**:

```python
from src.analysis.link_logic import create_fragment_link_with_context

url = "https://logbooks.jlab.org/entry/4346807"
timestamp = "14:30"

link = create_fragment_link_with_context(url, timestamp)
print(link)
# https://logbooks.jlab.org/entry/4346807#:~:text=Shift-,*14%3A30*,Fault

# With different timestamp
timestamp = "09:45"
link = create_fragment_link_with_context(url, timestamp)
print(link)
# https://logbooks.jlab.org/entry/4346807#:~:text=Shift-,*09%3A45*,Fault
```

**Fragment Syntax Breakdown**:

```
#:~:text=Shift-,*14%3A30*,Fault
        ^^^^^^^^^^^^^^^^^^^^^^^
        Text Fragment specification

Shift-      = Start text (prefix)
      ,     = Separator
       *    = Exact match marker
        14%3A30  = Target timestamp (encoded)
              ,  = Separator
               Fault = End text (suffix)
```

**How Browser Interprets This**:
- Searches for text that starts with "Shift"
- Looks for "14:30" immediately after
- Confirms "Fault" follows
- Scrolls to and highlights "14:30" with "Shift" and "Fault" as context

**Current Limitation**: `context_lines` parameter is **not used**. The function always uses hardcoded "Shift" and "Fault" strings regardless of the `context_lines` value.

---

## Usage in Pipeline

### Integration Point

Fragment links are generated during the **Fault Extraction** stage (`src/analysis/shift_summary.py`) and included in the output CSV.

### Output Format

**CSV Column**: `FragmentLink`

**Example Output**:
```csv
timestamp,description,entry_number,FragmentLink
14:30,RF issues detected,4346807,https://logbooks.jlab.org/entry/4346807#:~:text=14%3A30
08:15,Cooling system alarm,4346808,https://logbooks.jlab.org/entry/4346808#:~:text=08%3A15
```

### Code Integration

```python
# In src/analysis/shift_summary.py
from src.analysis.link_logic import create_text_fragment_link

def extract_faults(shift_summary: dict) -> list:
    """Extract faults and generate fragment links."""
    faults = []
    
    entry_url = f"https://logbooks.jlab.org/entry/{shift_summary['entry_number']}"
    
    for fault in shift_summary.get('faults', []):
        timestamp = fault['timestamp']
        
        # Generate fragment link
        fragment_link = create_text_fragment_link(entry_url, timestamp)
        
        faults.append({
            'timestamp': timestamp,
            'description': fault['description'],
            'FragmentLink': fragment_link
        })
    
    return faults
```

### Dashboard Integration

The Streamlit dashboard (`src/frontend/app.py`) renders fragment links as clickable hyperlinks:

```python
# In src/frontend/app.py
import streamlit as st

# Display fault with clickable link
for idx, fault in enumerate(faults):
    with st.expander(f"{fault['timestamp']} - {fault['description']}"):
        # Render fragment link as clickable URL
        st.markdown(f"**Logbook Entry:** [{fault['entry_number']}]({fault['FragmentLink']})")
```

**User Experience**:
1. User sees fault in dashboard
2. Clicks the fragment link
3. Browser opens JLab logbook entry
4. Page automatically scrolls to and highlights the timestamp
5. User sees fault context immediately

---

## Error Handling

### Invalid URL

**Symptom**: URL cannot be parsed

**Behavior**: Returns original URL unchanged (no fragment appended)

**Example**:
```python
link = create_text_fragment_link("not-a-valid-url", "14:30")
print(link)  # "not-a-valid-url"
```

**Code**:
```python
try:
    parsed = urlparse(url)
    # ... create fragment
except Exception:
    return url  # Return original on any error
```

### Empty or None Timestamp

**Symptom**: No timestamp provided

**Behavior**: Returns original URL unchanged

**Example**:
```python
link = create_text_fragment_link("https://logbooks.jlab.org/entry/4346807", "")
print(link)  # "https://logbooks.jlab.org/entry/4346807"

link = create_text_fragment_link("https://logbooks.jlab.org/entry/4346807", None)
print(link)  # "https://logbooks.jlab.org/entry/4346807"
```

**Code**:
```python
if not url or not timestamp:
    return url
```

### Special Characters in Timestamp

**Handled**: All special characters are URL-encoded

**Example**:
```python
# Timestamp with colon (normal case)
link = create_text_fragment_link(url, "14:30")
print(link)  # ...#:~:text=14%3A30

# Timestamp with spaces (edge case)
link = create_text_fragment_link(url, "14 30")
print(link)  # ...#:~:text=14%2030

# Timestamp with special chars
link = create_text_fragment_link(url, "Error#1")
print(link)  # ...#:~:text=Error%231
```

### Browser Compatibility

**Symptom**: Link doesn't scroll/highlight in Firefox or Safari

**Behavior**: Link opens page normally (no scroll/highlight)

**Workaround**: None - browser limitation

**Detection**:
```python
import platform
from urllib.parse import urlparse

def is_text_fragment_supported():
    """Check if current browser supports Text Fragments."""
    # Client-side detection only (Python can't detect browser)
    # User must check browser version manually
    return False  # Assume unsupported until confirmed
```

---

## Testing

### Unit Tests

```python
import pytest
from src.analysis.link_logic import create_text_fragment_link, create_fragment_link_with_context

def test_create_text_fragment_link_basic():
    """Test basic timestamp link generation."""
    url = "https://logbooks.jlab.org/entry/4346807"
    timestamp = "14:30"
    
    result = create_text_fragment_link(url, timestamp)
    
    assert result == "https://logbooks.jlab.org/entry/4346807#:~:text=14%3A30"

def test_create_text_fragment_link_with_seconds():
    """Test timestamp with seconds."""
    url = "https://logbooks.jlab.org/entry/4346807"
    timestamp = "08:15:30"
    
    result = create_text_fragment_link(url, timestamp)
    
    assert result == "https://logbooks.jlab.org/entry/4346807#:~:text=08%3A15%3A30"

def test_create_text_fragment_link_empty_timestamp():
    """Test empty timestamp returns original URL."""
    url = "https://logbooks.jlab.org/entry/4346807"
    
    result = create_text_fragment_link(url, "")
    
    assert result == url

def test_create_text_fragment_link_invalid_url():
    """Test invalid URL returns original URL."""
    url = "not-a-url"
    timestamp = "14:30"
    
    result = create_text_fragment_link(url, timestamp)
    
    assert result == url

def test_create_fragment_link_with_context():
    """Test context link generation."""
    url = "https://logbooks.jlab.org/entry/4346807"
    timestamp = "14:30"
    
    result = create_fragment_link_with_context(url, timestamp)
    
    assert "#:~:text=Shift-,*14%3A30*,Fault" in result
    assert result.startswith("https://logbooks.jlab.org/entry/4346807")

def test_create_fragment_link_with_context_encoding():
    """Test context link with special characters."""
    url = "https://logbooks.jlab.org/entry/4346807"
    timestamp = "08:15"
    
    result = create_fragment_link_with_context(url, timestamp)
    
    assert "08%3A15" in result  # Colon encoded
```

### Manual Testing

**Steps**:

1. **Generate link**:
   ```python
   from src.analysis.link_logic import create_text_fragment_link
   link = create_text_fragment_link("https://logbooks.jlab.org/entry/4346807", "14:30")
   print(link)
   ```

2. **Copy link** to clipboard

3. **Open in Chrome/Edge** (not Firefox/Safari)

4. **Verify**:
   - Page scrolls to "14:30"
   - Text is highlighted yellow
   - No errors in console

---

## Performance

### Computation Cost

**Time Complexity**: O(1) - constant time
- URL parsing: O(n) where n = URL length
- URL encoding: O(m) where m = timestamp length
- String concatenation: O(k) where k = fragment length

**Typical execution**: < 1ms

### Memory Usage

**Per Link**: ~100-200 bytes (URL string)

**Impact**: Negligible

---

## Troubleshooting

### Link Doesn't Scroll in Browser

**Possible Causes**:

1. **Unsupported browser**:
   - Firefox, Safari don't support Text Fragments yet
   - **Solution**: Use Chrome, Edge, or Opera

2. **Text not found on page**:
   - Timestamp might be formatted differently in logbook
   - **Solution**: Verify timestamp exists exactly as encoded

3. **Encoding mismatch**:
   - Browser might decode differently
   - **Solution**: Try different encoding (remove `safe=''`)

### Link Opens But Doesn't Highlight

**Possible Causes**:

1. **Multiple occurrences**: Browser scrolls to first match, but highlight might be on different instance
   - **Solution**: Use context-aware link (`create_fragment_link_with_context`)

2. **Dynamic content**: Page loads content asynchronously
   - **Solution**: Wait for page to fully load (browser handles this)

### Fragment Syntax Errors

**Symptom**: Browser shows 404 or ignores fragment

**Cause**: Invalid fragment syntax

**Debug**:
```python
url = "https://logbooks.jlab.org/entry/4346807"
timestamp = "14:30"

link = create_text_fragment_link(url, timestamp)
print(f"Generated: {link}")

# Verify fragment syntax
assert "#:~:text=" in link
assert "14%3A30" in link
```

### Timestamp Not Found in Logbook

**Symptom**: Link scrolls but no highlight

**Cause**: Timestamp format in logbook differs from our encoding

**Example**:
- Our timestamp: `"14:30"`
- Logbook format: `"14:30:00"` or `"2:30 PM"`

**Solution**: Normalize timestamp format before generating link

---

## Future Enhancements

### Dynamic Context Extraction

**Current**: Hardcoded "Shift" and "Fault" strings

**Proposed**: Extract actual surrounding text from logbook entry

```python
def create_fragment_link_with_dynamic_context(url: str, timestamp: str, lines_before: int = 2, lines_after: int = 2):
    """Fetch entry, extract context, generate fragment."""
    # 1. Fetch logbook entry HTML
    # 2. Parse to find timestamp location
    # 3. Extract surrounding text
    # 4. Generate fragment with actual context
    pass
```

### Fallback Mechanism

**Current**: Returns original URL on error

**Proposed**: Try multiple fragment formats

```python
def create_robust_fragment_link(url: str, timestamp: str):
    """Try multiple fragment formats, fall back gracefully."""
    formats = [
        create_text_fragment_link(url, timestamp),
        create_fragment_link_with_context(url, timestamp),
        # Try variations
        create_text_fragment_link(url, timestamp.replace(":", "%3A")),
    ]
    # Return first valid link
    return formats[0]
```

### Browser Detection

**Proposed**: Detect browser support and adapt

```python
def create_browser_aware_fragment_link(url: str, timestamp: str):
    """Generate link appropriate for current browser."""
    if browser_supports_text_fragments():
        return create_text_fragment_link(url, timestamp)
    else:
        # Fallback: anchor link or plain URL
        return url
```

---

## Related Documentation

- [Fault Extraction](../pipeline/PIPELINE_FAULT_EXTRACTION.md) - Link generation in pipeline
- [Output Formats](../config/OUTPUT_FORMATS.md) - FragmentLink column specification
- [Dashboard](../getting-started/DASHBOARD.md) - Link rendering in UI
- [Architecture](../pipeline/ARCHITECTURE.md) - Link integration design

---

*For pipeline integration details, see [PIPELINE_FAULT_EXTRACTION.md](../pipeline/PIPELINE_FAULT_EXTRACTION.md).*

---

**External References**:
- [Text Fragments Spec](https://web.dev/text-fragment/)
- [MDN: Text Fragments](https://developer.mozilla.org/en-US/docs/Web/API/Text_Fragments_API)
- [Chrome Blog: Text Fragments](https://blog.chromium.org/2020/02/Text-fragments-in-Chrome.html)