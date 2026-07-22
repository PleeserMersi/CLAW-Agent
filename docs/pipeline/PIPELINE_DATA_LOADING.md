# Data Loading Pipeline

Detailed documentation for the data loading stage of CLAW-Agent.

---

## Overview

The data loading stage fetches shift summaries from Jefferson Lab's logbook API and converts them into a structured DataFrame for downstream processing.

**Module**: `src/data/data_loading.py`

**Pipeline Position**: Stage 1 (first stage)

**Input**: Date range, hall selection

**Output**: pandas DataFrame with shift summaries

---

## Data Source

### JLab Logbook API

**Base URL**: `https://logbooks.jlab.org/api/elog`

**Authentication**: HTTP Basic Auth (username/password)

**Endpoints Used**:
- `GET /entries` - Fetch logbook entries with pagination
- `GET /entries/{lognumber}` - Fetch single entry by number

### Hall to Logbook Mapping

| Hall | Logbook ID | Description |
|------|------------|-------------|
| hall_a | halog | Hall A Operational Logbook |
| hall_b | hblog | Hall B Operational Logbook |
| hall_c | hclog | Hall C Operational Logbook |
| hall_d | hdlog | Hall D Operational Logbook |

### Excluded Logbooks

By default, the following logbooks are excluded:
- `-3`: Special/test logbook
- `-5`: Special/test logbook

Can be customized via `EXCLUDED_LOGBOOKS` in `config.py`.

---

## API Request Structure

### Fetch Parameters

```python
params = {
    "startdate": "2024-01-01",      # Start date (YYYY-MM-DD)
    "enddate": "2024-01-31",        # End date (YYYY-MM-DD)
    "title": "Shift Summary",       # Title filter
    "field": [                      # Fields to retrieve
        "lognumber",
        "title",
        "created",
        "body"
    ],
    "book": ["halog", "hblog"],     # Logbook IDs
    "page": 0                       # Page number (0-indexed)
}
```

### Response Format

```json
{
  "stat": "ok",
  "data": {
    "currentItems": 10,
    "totalItems": "10",
    "pageLimit": 50,
    "currentPage": 0,
    "pageCount": 1,
    "entries": [
      {
        "lognumber": "4346807",
        "title": "Shift Summary : 04.02.2025 Owl shift",
        "created": {
          "string": "2025-04-02 01:23:00",
          "format": "yyyy-MM-dd HH:mm:ss"
        },
        "body": {
          "format": "text/html",
          "content": "<html>...</html>"
        },
        "_hall": "hall_c"  # Added by CLAW-Agent
      }
    ]
  }
}
```

---

## Processing Pipeline

### Step 1: Fetch Shift Summaries

**Function**: `fetch_shift_summaries()`

**Process**:
1. Initialize `CachedAPIClient` with credentials
2. For each selected hall:
   - Build API request parameters
   - Fetch page 0
   - Process entries
   - Continue to next page until exhausted
   - Add 500ms delay between requests (rate limiting)
3. Combine all entries from all halls
4. Return combined JSON response

**Pagination Logic**:
```python
while True:
    result = api_client.get(url, params)
    entries = result['data']['entries']
    
    if not entries:
        break
    
    all_entries.extend(entries)
    current_page += 1
    
    if current_page >= page_count:
        break
    
    time.sleep(API_DELAY_SECONDS)
```

**Caching**:
- Responses cached for 30 minutes
- Cache key: MD5 hash of URL + sorted params
- Reduces redundant API calls during development/testing

---

### Step 2: Convert to DataFrame

**Function**: `process_json_to_dataframe()`

**Process**:
1. Load JSON data (from parameter or file)
2. Extract entries using `pd.json_normalize()` with field paths
3. Rename columns to PascalCase
4. Add `LogbookURL` column from `LogNumber`
5. Map `_hall` field to `Hall` column (formatted as "Hall A", "Hall B", etc.)
6. Normalize content in batch (HTML → text or whitespace cleanup)
7. Normalize titles using `normalize_shift_title()`
8. Drop rows with NaN content and duplicate content entries
9. Reorder columns to standard schema

**DataFrame Schema**:

| Column | Type | Description |
|--------|------|-------------|
| `LogNumber` | int | Logbook entry number |
| `LogbookURL` | str | Full URL to logbook entry |
| `Title` | str | Normalized entry title |
| `Date` | str | Creation date (YYYY-MM-DD HH:MM:SS) |
| `DateTime` | datetime | Parsed datetime object |
| `Format` | str | Content format (html/text) |
| `Content` | str | Raw HTML or text content |
| `Hall` | str | Hall name ("Hall A", "Hall B", etc.) |
| `NormalizedContent` | str | Cleaned text content (HTML stripped, whitespace normalized) |

**Column Creation**:
```python
# json_normalize with field paths
df = pd.json_normalize(
    entries,
    sep='_',
    meta=[
        'lognumber',
        'title',
        ['created', 'string'],
        ['body', 'format'],
        ['body', 'content']
    ]
)

# Rename columns
df = df.rename(columns={
    'lognumber': 'LogNumber',
    'title': 'Title',
    'created_string': 'Date',
    'body_format': 'Format',
    'body_content': 'Content'
})

# Add URL
df['LogbookURL'] = df['LogNumber'].apply(lambda x: f"https://logbooks.jlab.org/entry/{x}")

# Map _hall to Hall (formatted)
df['Hall'] = df['_hall'].str.replace('_', ' ').str.title()
```

**Content Normalization**:
```python
def normalize_row(row):
    content = row.get('Content', '')
    format_type = row.get('Format', '')
    
    if is_html(format_type, content):
        return html_to_text(content)  # BeautifulSoup html.parser
    else:
        return clean_text(content)    # Whitespace normalization

df['NormalizedContent'] = df.apply(normalize_row, axis=1)

# Normalize titles
df['Title'] = df['Title'].apply(normalize_shift_title)

# Drop NaN content and duplicates
df = df.dropna(subset=['Content']).drop_duplicates(subset=['Content'])
```

---

### Step 3: Save to Disk

**Function**: `main_function1()` (pipeline entry point)

**Output Files**:
1. `data/raw/shift_summary.JSON` - Raw JSON response
2. `data/raw/shift_summary.csv` - Processed DataFrame

**Process**:
1. Fetch data from API
2. Save raw JSON for debugging
3. Convert to DataFrame
4. Save CSV for downstream stages
5. Log statistics (count, date range, hall distribution)

**Code**:
```python
# Save raw JSON
with open(SHIFT_SUMMARY_JSON, 'w', encoding='utf-8') as f:
    json.dump(json_data, f, indent=4)
logger.info(f"Saved raw data to {SHIFT_SUMMARY_JSON}")

# Process to DataFrame
df = process_json_to_dataframe(json_data, halls=halls)

# Save CSV
df.to_csv(SHIFT_SUMMARY_CSV, index=False)
logger.info(f"Saved {len(df)} shift summaries to {SHIFT_SUMMARY_CSV}")

# Log statistics
logger.info(f"Date range: {df['DateTime'].min()} to {df['DateTime'].max()}")
logger.info(f"Hall distribution: {df['Hall'].value_counts().to_dict()}")
```

---

## Data Flow Diagram

```
JLab Logbook API
       │
       ▼
┌──────────────────┐
│ CachedAPIClient  │
│ (with caching)   │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ Pagination Loop  │
│ (all pages)      │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ Add Hall Info    │
│ (_hall column)   │
└──────────────────┘
       │
       ▼
┌──────────────────┐
│ JSON Response    │
└──────────────────┘
       │
       ├─────────────────┐
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ Raw JSON     │  │ JSON → DataFrame
│ (cached)     │  │              │
└──────────────┘  └──────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ HTML → Text  │
                   │ Normalize    │
                   └──────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ shift_summary.csv
                   └──────────────┘
```

---

## Caching Strategy

### LRU Cache Implementation

**Class**: `CachedAPIClient` (in `cache_utils.py`)

**Configuration**:
- **Max Size**: 200 entries
- **TTL**: 30 minutes (1800 seconds)
- **Key Generation**: MD5 hash of URL + sorted params

**Cache Key Example**:
```python
url = "https://logbooks.jlab.org/api/elog/entries"
params = {"startdate": "2024-01-01", "page": 0}
cache_key = md5("https://logbooks.jlab.org/api/elog/entries:{"page": 0, "startdate": "2024-01-01"}")
```

### Cache Behavior

**Cache Hit**:
- Return cached response immediately
- No network request
- Log debug message

**Cache Miss**:
- Make API request
- Store response in cache
- Return response

**Cache Expiration**:
- Check timestamp on get()
- Delete if older than TTL
- Return None (triggers fresh fetch)

### When Cache Helps

1. **Development/Testing**: Same date range multiple times
2. **Pipeline Retries**: Failed stage, restart from beginning
3. **Multi-stage Runs**: Verification needs original data

### When Cache Doesn't Help

1. **New Date Ranges**: Always cache miss
2. **Long Runs**: Data expires during execution
3. **Real-time Needs**: Need fresh data every time

---

## Error Handling

### API Failures

**Symptoms**:
- `API request failed: [error message]`
- Returns `None` instead of data

**Causes**:
- Network connectivity issues
- Authentication failures
- Rate limiting (429)
- Server errors (5xx)

**Handling**:
```python
try:
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    result = response.json()
except requests.RequestException as e:
    print(f"API request failed: {e}")
    return None
```

**Recovery**:
- Retry logic in pipeline orchestrator
- Manual intervention for auth issues
- Check network connectivity

### Empty Results

**Symptoms**:
- `No data loaded. Aborting.`
- Pipeline exits early

**Causes**:
- Date range has no entries
- Invalid hall names
- Title filter too restrictive

**Handling**:
```python
if shift_df is None or len(shift_df) == 0:
    logger.error("No data loaded. Aborting.")
    return
```

**Recovery**:
- Expand date range
- Check hall names
- Remove title filter

### HTML Parsing Errors

**Symptoms**:
- Content not cleaned properly
- HTML tags in output

**Causes**:
- Malformed HTML
- Unsupported tags
- Encoding issues

**Handling**:
```python
try:
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator=' ', strip=True)
except Exception as e:
    logger.warning(f"HTML parsing failed: {e}")
    text = html_content  # Fallback: use raw content
```

---

## Performance Optimization

### Pagination Efficiency

**Current**: Fetch all pages sequentially

**Optimization**: Parallel page fetching (not implemented)

```python
# Potential improvement
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(fetch_page, page) for page in range(total_pages)]
    all_entries = [f.result() for f in as_completed(futures)]
```

### Caching Benefits

**Without Cache**:
- 100 entries = 2 pages = 2 API calls per run
- 10 runs = 20 API calls

**With Cache**:
- 100 entries = 2 API calls (first run)
- 10 runs = 2 API calls (cached)

**Savings**: 90% reduction in API calls for repeated runs

### Memory Usage

**DataFrame Size**:
- 100 entries × 10KB each = 1MB (with HTML content)
- 1000 entries × 10KB each = 10MB
- 10000 entries × 10KB each = 100MB

**Recommendation**: Process date ranges ≤ 30 days to keep memory manageable. For larger ranges, consider splitting into smaller date chunks.

---

## Usage Examples

### Basic Usage (Pipeline)

```bash
./scripts/run_pipeline.sh --start-date 2024-01-01 --end-date 2024-01-31
```

### Direct Module Usage

```python
from src.data.data_loading import main_function1

# Load data for specific date range and halls
df = main_function1(
    start="2024-01-01",
    end="2024-01-31",
    halls=["hall_a", "hall_c"]
)

print(f"Loaded {len(df)} shift summaries")
print(f"Columns: {df.columns.tolist()}")
print(f"Date range: {df['DateTime'].min()} to {df['DateTime'].max()}")
print(f"Hall distribution:\n{df['Hall'].value_counts()}")
```

### Fetch Single Entry

```python
from src.utils.cache_utils import CachedAPIClient
from src.config import JLAB_LOGBOOK_BASE_URL, JLAB_USERNAME, JLAB_PASSWORD

api = CachedAPIClient(
    base_url=JLAB_LOGBOOK_BASE_URL,
    username=JLAB_USERNAME,
    password=JLAB_PASSWORD
)

entry = api.get_single_entry("4346807")
print(entry['data']['entry']['body']['content'])
```

### Manual API Call

```python
from src.data.data_loading import fetch_shift_summaries

result = fetch_shift_summaries(
    start_date="2024-01-01",
    end_date="2024-01-02",
    halls=["hall_c"]
)

print(f"Total items: {result['data']['totalItems']}")
for entry in result['data']['entries']:
    print(f"{entry['lognumber']}: {entry['title']} (Hall: {entry['_hall']})")
```

---

## Testing

### Unit Tests

**Test Fetch Function**:
```python
def test_fetch_shift_summaries():
    result = fetch_shift_summaries(
        start_date="2024-01-01",
        end_date="2024-01-02",
        halls=["hall_c"]
    )
    
    assert result is not None
    assert result['stat'] == 'ok'
    assert 'entries' in result['data']
    assert all('_hall' in entry for entry in result['data']['entries'])
```

**Test DataFrame Conversion**:
```python
def test_process_json_to_dataframe():
    json_data = {...}  # Sample JSON
    df = process_json_to_dataframe(json_data=json_data)
    
    assert df is not None
    assert 'LogNumber' in df.columns
    assert 'NormalizedContent' in df.columns
    assert 'Hall' in df.columns
    assert len(df) > 0
    
    # Check column types
    assert df['LogNumber'].dtype in ['int64', 'int32']
    assert pd.api.types.is_datetime64_any_dtype(df['DateTime'])
```

### Integration Tests

**Full Data Loading Pipeline**:
```python
def test_data_loading_integration():
    df = main_function1(
        start="2024-01-01",
        end="2024-01-02",
        halls=["hall_c"]
    )
    
    assert df is not None
    assert len(df) > 0
    
    # Check files created
    assert SHIFT_SUMMARY_JSON.exists()
    assert SHIFT_SUMMARY_CSV.exists()
    
    # Check expected columns
    expected = ['LogNumber', 'LogbookURL', 'Title', 'Date', 'DateTime', 
                'Format', 'Content', 'Hall', 'NormalizedContent']
    for col in expected:
        assert col in df.columns, f"Missing column: {col}"
```

---

## Troubleshooting

### "API request failed"

**Check**:
1. Internet connectivity
2. JLab API status
3. Credentials in `.env`
4. Firewall/proxy settings

**Debug**:
```bash
# Test API manually
curl -u JLAB_USERNAME:JLAB_PASSWORD \
  "https://logbooks.jlab.org/api/elog/entries?startdate=2024-01-01&enddate=2024-01-02"
```

### "No entries found"

**Check**:
1. Date range has shift summaries posted
2. Hall names are correct (`hall_a`, `hall_b`, `hall_c`, `hall_d`)
3. Logbooks exist for those halls
4. `SEARCH_TITLE` filter matches actual titles

**Debug**:
```python
# Check available halls
from src.config import HALL_LOGBOOKS
print(HALL_LOGBOOKS)

# Test with all halls (no filter)
df = main_function1("2024-01-01", "2024-01-02", halls=None)  # None = all halls

# Check what titles are being searched
from src.config import SEARCH_TITLE
print(f"Searching for titles containing: '{SEARCH_TITLE}'")
```

### "HTML not cleaned"

**Check**:
1. BeautifulSoup installed (`pip install beautifulsoup4`)
2. HTML content is valid
3. Format field is "html" for HTML content

**Debug**:
```python
from src.utils.text_utils import html_to_text, clean_text

html = "<p>Test <b>content</b></p>"
text = html_to_text(html)
print(text)  # Should be: "Test content"

# Check format detection
format_type = "html"
content = "<html>...</html>"
is_html = format_type == 'html' or '<html>' in content.lower()
print(f"Is HTML: {is_html}")
```

---

## Related Documentation

- [Configuration](./CONFIGURATION.md) - API credentials and settings
- [Architecture](./ARCHITECTURE.md) - Overall system design
- [Caching](./UTILS_CACHE.md) - Cache implementation details
- [Text Processing](./UTILS_TEXT.md) - HTML cleaning utilities

---

*For pipeline orchestration details, see [OPERATIONS_PIPELINE.md](./OPERATIONS_PIPELINE.md).*