# System Architecture

Comprehensive overview of CLAW-Agent's architecture and design patterns.

---

## High-Level Architecture

CLAW-Agent follows a **pipeline pattern** with parallel processing capabilities. Each stage transforms data and passes it to the next stage, with optional branching for error handling.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLAW-Agent System                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │  Config     │──▶│  Pipeline   │───▶│   Data      │                  │
│  │  Manager    │    │ Orchestrator│    │  Loading    │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                  │
│         │                  │                  │                         │
│         │                  │                  ▼                         │
│         │                  │         ┌─────────────┐                    │
│         │                  │         │ Shift       │                    │
│         │                  │         │ Summaries   │                    │
│         │                  │         │ (DataFrame) │                    │
│         │                  │         └─────────────┘                    │
│         │                  │                  │                         │
│         │                  │                  ▼                         │
│         │                  │    ┌─────────────────────────┐             │
│         │                  │    │  Parallel Worker Pool   │             │
│         │                  │    │  (ThreadPoolExecutor)   │             │
│         │                  │    └─────────────────────────┘             │
│         │                  │                  │                         │
│         │                  ▼                  ▼                         │
│         │         ┌──────────────────────────────────┐                  │
│         │         │      Pipeline Stages             │                  │
│         │         ├──────────────────────────────────┤                  │
│         │         │ 1. Fault Extraction (LLM)        │                  │
│         │         │ 2. Fault Filtering (LLM) [opt]   │                  │
│         │         │ 3. Tag Classification (ChromaDB) │                  │
│         │         │ 4. Timestamp Verification (LLM)  │                  │
│         │         │ 5. Timestamp Fixing (LLM)        │                  │
│         │         │ 6. Consolidation (Merge)         │                  │
│         │         └──────────────────────────────────┘                  │
│         │                  │                                            │
│         │                  ▼                                            │
│         │         ┌──────────────────────┐                              │
│         │         │   Output Files       │                              │
│         │         │   - all_shift_faults.csv                            │
│         │         │   - manual_check.csv                                │
│         │         └──────────────────────┘                              │
│         │                  │                                            │
│         │                  ▼                                            │
│         │         ┌──────────────────────┐                              │
│         │         │  Streamlit Dashboard │                              │
│         │         └──────────────────────┘                              │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │  Utilities  │    │  Caching    │    │  Logging    │                  │
│  │  - LLM      │    │  - LRU      │    │  - File     │                  │
│  │  - Text     │    │  - TTL      │    │  - Console  │                  │
│  │  - Shutdown │    │  - API      │    │  - Levels   │                  │
│  └─────────────┘    └─────────────┘    └─────────────┘                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### 1. Core Orchestrator (`pipeline.py`)

**Responsibilities:**
- Parse command-line arguments
- Validate configuration
- Manage SSH tunnels
- Coordinate pipeline stages
- Handle graceful shutdown
- Track timing and performance

**Key Methods:**
```python
run_pipeline(start_date, end_date, verbose, agent, filter_faults_flag,
             max_workers, extract_batch_size, tag_batch_size,
             filter_batch_size, validation_batch_size, fixing_batch_size, halls)

run_pipeline_with_tunnel(...)  # Adds SSH tunnel management
```

**Design Pattern:** Facade - provides simplified interface to complex subsystem

---

### 2. Configuration Manager (`config.py`)

**Responsibilities:**
- Load environment variables from `.env`
- Validate configuration values
- Manage file paths and directories
- Parse SSH tunnel configurations
- Provide centralized access to settings

**Key Components:**
- `HALL_LOGBOOKS`: Hall to logbook ID mapping
- `DEFAULT_HALLS`: Default halls to process
- `SSH_TUNNELS`: Dynamic SSH port forwarding
- `validate_config()`: Configuration validation
- `validate_config_strict()`: Fail-fast validation

**Design Pattern:** Singleton - single source of truth for configuration

---

### 3. Data Loading (`data/data_loading.py`)

**Responsibilities:**
- Fetch shift summaries from JLab API
- Handle pagination
- Map logbook IDs to hall names
- Cache API responses
- Convert JSON to pandas DataFrame

**Key Methods:**
```python
fetch_shift_summaries(start_date, end_date, halls, excluded_books,
                      search_title, username, password)

process_json_to_dataframe(json_data, json_file, normalize, halls)

main_function1(start_date, end_date, halls)  # Pipeline entry point
```

**Design Pattern:** Repository - abstracts data access layer

---

### 4. Analysis Modules (`analysis/`)

#### 4.1 Fault Extraction (`shift_summary.py`)

**Purpose:** Extract faults from shift summaries using LLM

**Key Features:**
- Batch processing (multiple summaries per LLM call)
- Parallel execution with `ThreadPoolExecutor`
- Timestamp normalization (12h ↔ 24h conversion via `text_utils.normalize_timestamp`)
- Fallback timestamp extraction for edge cases (military time without colon, time ranges, etc.)
- Text fragment link generation via `link_logic.create_text_fragment_link`
- Pydantic models for structured JSON output validation

**Data Flow:**
```
Shift Summaries (DataFrame from data_loading.py)
    │
    ▼
┌─────────────────────────────┐
│ Batch by extract_batch_size │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ LLM Prompt (JSON extraction)│
│ Pydantic Fault models       │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Parse JSON → Fault Objects  │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Normalize Timestamps        │
│ (normalize_timestamp)       │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Generate Fragment Links     │
│ (link_logic.create_...)     │
└─────────────────────────────┘
    │
    ▼
Faults DataFrame (with FragmentLink column)
```

**Key Methods:**
```python
extract_faults_batch(batch_data, agent, max_workers, batch_size)
_extract_fallback_timestamp(timestamp_str)    # Edge case handling
normalize_timestamp(timestamp)                # From text_utils
create_text_fragment_link(url, timestamp)     # From link_logic
```

**File Location:** `src/analysis/shift_summary.py`

---

#### 4.2 Fault Filtering (`fault_filter.py`)

**Purpose:** Validate extracted faults and remove non-fault entries

**Key Features:**
- LLM-based validation (Yes/No classification)
- Batch processing for efficiency
- Conservative default (keep if uncertain)
- Separate output for removed items

**Decision Criteria for Valid Faults:**

**Valid Faults**

- Errors, crashes, delays
- Alarms, trips, reboots
- Failures, issues, problems
- Shutdowns

**Invalid Faults**
  
- Routine operations
- Normal status updates
- Informational notes
- Trivia or jokes

**Key Methods:**
```python
is_valid_fault(description, agent)
validate_faults_batch(batch_data, agent)
filter_faults(faults_df, agent, max_workers, batch_size)
```

---

#### 4.3 Tag Extraction (`tag_extraction.py`)

**Purpose:** Classify faults into 16 categories using semantic search

**Key Features:**
- ChromaDB vector database for embeddings
- Keyword-based candidate retrieval
- LLM-based final classification
- Batch processing support
- Persistent tag collection

**Tag Categories:**
1. Accelerator
2. Injector / Source
3. Beam Diagnostics
4. Halls
5. Cryogenics
6. Vacuum
7. Magnets
8. Targets
9. EPICS
10. Power
11. Safety
12. Radiation Control (RadCon)
13. Network
14. CODA
15. Mechanical
16. MCC

**Data Flow:**
```
Faults DataFrame
    │
    ▼
┌─────────────────────────────┐
│ Load Tag Database (JSON)    │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ ChromaDB Semantic Search    │
│ (Top 5 candidates)          │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ LLM Classification          │
│ (Select 1 from candidates)  │
└─────────────────────────────┘
    │
    ▼
Faults with Tags
```

**Key Methods:**
```python
get_candidate_tags(description, top_k=5)
classify_fault_batch(batch_data, agent, max_workers, batch_size)
main_tagger(faults_df, start_time, agent, max_workers, batch_size)
```

---

#### 4.4 Timestamp Verification (`accuracy_test.py`)

**Purpose:** Verify extracted timestamps match source summaries

**Key Features:**
- 15-minute tolerance threshold
- LLM-based verification (Yes/No)
- Batch processing
- Separation into accurate/inaccurate

**Verification Rules:**
1. Timestamp EXISTS in fault information
2. Timestamp is within 15 minutes of time in shift summary

**Data Flow:**
```
Faults DataFrame + Shift Summaries
    │
    ▼
┌─────────────────────────────┐
│ Batch by validation_batch_size
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ LLM Verification Prompt     │
│ (Compare timestamp + desc)  │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Parse Results               │
└─────────────────────────────┘
    │
    ├───▶ Accurate Faults
    └───▶ Inaccurate Faults
```

**Key Methods:**
```python
verify_timestamp_accuracy(fault_row, shift_summary, agent)
verify_timestamps_batch(batch_data, shift_summary, agent)
verify_faults(agent, max_workers, batch_size)
```

---

#### 4.5 Timestamp Fixing (`fixer.py`)

**Purpose:** Correct inaccurate timestamps by extracting the correct time from full logbook entries

**Key Features:**
- Fetch full logbook entry via JLab API (uses `CachedAPIClient`)
- LLM-based timestamp extraction from logbook content
- **24:00 (midnight) handling**: LLM may return "24:00"; caller converts to "00:00" with date rollover (+1 day)
- Re-verification after fixing (confirms fix is accurate)
- Low-confidence flagging for fixes that fail re-verification
- **Batch processing support**: Groups faults by log number, processes multiple faults from same entry together
- **Batched re-verification**: Re-verifies all fixes in batches for efficiency

**Special Case: 24:00 (Midnight Rollover)**
- LLM returns "24:00" for midnight events
- Caller in `fixer.py` detects this and:
  1. Parses current `FullTimestamp`
  2. Adds 1 day to the date
  3. Sets time to "00:00"
  4. Stores "00:00" in CSV (not "24:00")

**Data Flow:**
```
Inaccurate Faults (from accuracy_test.py)
    │
    ▼
┌─────────────────────────────┐
│ Group by LogNumber          │
│ (same log = same entry)     │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Fetch Full Logbook Entry    │
│ (via CachedAPIClient)       │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ LLM Extract Correct Time    │
│ (batch or single)           │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Handle 24:00 Rollover       │
│ (if timestamp == "24:00")   │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Re-verify Timestamp         │
│ (batch re-verification)     │
└─────────────────────────────┘
    │
    ├───▶ fixed.csv (high confidence, passed re-verify)
    └───▶ manual_check.csv (low confidence or failed re-verify)
```

**Key Methods:**
```python
extract_correct_timestamp(desc, logbook, agent)  # Single extraction
fix_timestamps_batch(batch, logbook, agent)      # Batch extraction
_fix_single_timestamp(row, summaries, agent)     # Worker for single
_process_logbook_batch(batch, log_num, agent)    # Worker for batch
fix_timestamps(agent, max_workers, batch_size)   # Main orchestrator
_batched_reverify_fixed(candidates, batch_size)  # Batch re-verify
get_logbook_entry_by_log_number(log_num)         # API fetch
```

**File Location:** `src/analysis/fixer.py`

---

#### 4.6 Consolidation (`verifyer.py`)

**Purpose:** Merge verified and fixed faults into final output

**Key Features:**
- Combine `accurate.csv` + `fixed.csv` into single DataFrame
- Add `verification_status` column ('accurate' or 'fixed')
- Append to existing `all_shift_faults.csv` (preserves history across runs)
- Sort by `FullTimestamp`
- Ensure all expected columns present (fills missing with None)

**Data Flow:**
```
accurate.csv + fixed.csv
    │
    ▼
┌─────────────────────────────┐
│ Load both CSVs              │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Add verification_status     │
│ (accurate vs fixed)         │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Concatenate DataFrames      │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Sort by FullTimestamp       │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Append to all_shift_faults  │
│ (header if new, else data)  │
└─────────────────────────────┘
    │
    ▼
Final Output
```

**Key Methods:**
```python
consolidate_faults(agent)      # Core merge logic
final_verification(agent)      # Wrapper with logging
main_function5(agent)          # Entry point
```

**File Location:** `src/analysis/verifyer.py`

---

### 5. Utility Modules (`utils/`)

#### 5.1 LLM Utilities (`llm_utils.py`)

**Purpose:** Interface with OpenClaw agents

**Features:**
- Subprocess-based LLM calls
- Retry logic with exponential backoff
- Timeout handling
- Shutdown interruptibility
- Centralized prompt templates

**Prompt Templates:**
- `fault_extraction`: Extract faults from summaries
- `tagger_prompt`: Classify fault with tags
- `timestamp_verification`: Verify timestamp accuracy
- `timestamp_correction`: Extract correct timestamp
- `fault_validation`: Validate if entry is fault
- `*_batch`: Batch versions for efficiency

**Key Methods:**
```python
call_llm(prompt, agent, timeout_seconds, max_retries, retry_delay)
```

---

#### 5.2 Text Utilities (`text_utils.py`)

**Purpose:** Text processing and timestamp handling

**Features:**
- HTML to text conversion
- Whitespace normalization
- Timestamp parsing (12h ↔ 24h)
- Datetime construction
- Time extraction from text

**Key Methods:**
```python
html_to_text(html_content)
clean_text(text)
normalize_timestamp(timestamp)
parse_timestamp_to_datetime(date_str, time_str)
extract_time_from_text(text)
```

---

#### 5.3 Cache Utilities (`cache_utils.py`)

**Purpose:** Reduce redundant API calls

**Features:**
- LRU cache with TTL
- URL + params → cache key (MD5 hash)
- Automatic eviction
- 30-minute default TTL
- 200 entry capacity

**Key Classes:**
```python
class LRUCache:
    get(key)
    set(key, value)
    clear()

class CachedAPIClient:
    get(url, params, use_cache)
    get_single_entry(lognumber)
    clear_cache()
```

---

#### 5.4 Logging Utilities (`logging_utils.py`)

**Purpose:** Centralized logging configuration

**Features:**
- Console + file handlers
- Configurable log levels
- Timestamp formatting
- Module-specific loggers

**Usage:**
```python
from utils.logging_utils import logger

logger.info("Message")
logger.warning("Warning")
logger.error("Error")
logger.debug("Debug")
```

---

#### 5.5 Shutdown Utilities (`shutdown.py`)

**Purpose:** Graceful interrupt handling

**Features:**
- SIGINT (Ctrl+C) handling
- Thread-safe shutdown flag
- Worker interruptibility
- Force exit on double Ctrl+C

**Key Functions:**
```python
setup_shutdown_handler()
is_shutdown_requested()
wait_for_shutdown(timeout)
request_shutdown()
clear_shutdown()
```

---

#### 5.6 Link Logic (`link_logic.py`)

**Purpose:** Generate clickable text fragment URLs for timestamps

**Features:**
- Text fragment URLs (Web API standard)
- Context-aware linking (prefix/suffix support)
- URL encoding for special characters (e.g., colons in timestamps)

**Text Fragment Syntax:**
```
https://logbooks.jlab.org/entry/12345#:~:text=14%3A30
```

**Key Methods:**
```python
create_text_fragment_link(url, timestamp, separator)          # Basic link
create_fragment_link_with_context(url, timestamp, ctx_lines)  # With context
```

**Usage:**
- Called during fault extraction to add `FragmentLink` column
- Links point to specific timestamps in logbook entries
- Browser scrolls to first occurrence of timestamp text

**File Location:** `src/analysis/link_logic.py`

---

## Data Flow Architecture

### Complete Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    1. DATA LOADING                              │
│                                                                 │
│  JLab API → CachedAPIClient → JSON → DataFrame                  │
│  Columns: LogNumber, Title, Created, Content, _hall             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    2. FAULT EXTRACTION                          │
│                                                                 │
│  DataFrame → Batch → LLM → JSON → DataFrame                     │
│  Columns: timestamp, description, run_number, ShiftLogNumber... │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (optional)
┌─────────────────────────────────────────────────────────────────┐
│                    2.4. FAULT FILTERING                         │
│                                                                 │
│  DataFrame → Batch → LLM → Split → DataFrame (faults)           │
│  Output: faults + removed (non-faults)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    2.5. TAGGING                                 │
│                                                                 │
│  DataFrame → Batch → ChromaDB → LLM → DataFrame                 │
│  Adds: tag column                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    3. TIMESTAMP VERIFICATION                    │
│                                                                 │
│  DataFrame + Shift Summaries → Batch → LLM → Split              │
│  Output: accurate.csv + inaccurate.csv                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    4. TIMESTAMP FIXING                          │
│                                                                 │
│  Inaccurate → Fetch Logbook → LLM → Fix → Re-verify → Split     │
│  Output: fixed.csv + manual_check.csv                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    5. CONSOLIDATION                             │
│                                                                 │
│  Accurate + Fixed → Merge → Sort → Append → Final CSV           │
│  Output: all_shift_faults.csv                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    6. DASHBOARD                                 │
│                                                                 │
│  CSV → Streamlit → Visualization                                │
│  Features: Timeline, Tags, Halls, Co-occurrence                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Threading Model

### ThreadPoolExecutor Usage

**Worker Pool Configuration:**
```python
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = [executor.submit(worker_func, item) for item in batch]
    results = [future.result() for future in as_completed(futures)]
```

**Parallelization Points:**
1. Fault extraction (by batch)
2. Fault filtering (by batch)
3. Tag classification (by batch)
4. Timestamp verification (by batch)
5. Timestamp fixing (by batch)

**Shutdown Coordination:**
```python
def worker_func(item):
    if is_shutdown_requested():
        return None  # Exit early
    # Process item
    return result
```

---

## Caching Strategy

### API Response Cache

**LRU Cache Parameters:**
- **Max Size**: 200 entries
- **TTL**: 30 minutes (1800 seconds)
- **Key**: MD5 hash of URL + sorted params

**Cache Hits:**
- Return cached response immediately
- No network call
- No LLM call needed

**Cache Misses:**
- Make API request
- Store response in cache
- Return response

### ChromaDB Persistent Storage

**Tag Embeddings:**
- Stored in `tag_db/chroma_db/`
- Persisted across runs
- Auto-initialized on first run
- Collection: `fault_tags`

---

## Error Handling Strategy

### Retry Logic

**LLM Calls:**
```python
for attempt in range(1, max_retries + 1):
    try:
        result = call_llm(...)
        return result
    except TimeoutExpired:
        wait_time = retry_delay * (2 ** (attempt - 1))
        time.sleep(wait_time)
```

**Exponential Backoff:**
- Attempt 1: Immediate
- Attempt 2: 2 seconds
- Attempt 3: 4 seconds

### Graceful Degradation

**Missing Data:**
- Empty fault list → Continue with empty DataFrame
- Failed API call → Log warning, skip entry
- Invalid timestamp → Skip fault, log warning

**Conservative Defaults:**
- Validation failure → Keep fault (don't discard)
- Tagging failure → Use "Other" tag
- Verification failure → Mark as inaccurate (not dropped)

---

## Security Considerations

### Credential Management

**Environment Variables:**
```bash
JLAB_USERNAME=...
JLAB_PASSWORD=...
SSH_USERNAME=...
SSH_HOST=...
```

**Best Practices:**
- Never commit `.env` to version control
- Use `.gitignore` for sensitive files
- Rotate credentials periodically

### SSH Tunnel Security

**Port Forwarding:**
```bash
ssh -L 8000:127.0.0.1:8001 \
    -L 11435:127.0.0.1:11434 \
    user@host
```

**Benefits:**
- Encrypted connection
- No direct internet exposure
- JLab internal network access

---

## Performance Characteristics

### Time Complexity

| Stage | Complexity | Notes |
|-------|------------|-------|
| Data Loading | O(n) | n = number of shift summaries |
| Fault Extraction | O(n/b) | b = batch_size, parallel |
| Fault Filtering | O(m/b) | m = number of faults |
| Tagging | O(m/b) | ChromaDB search + LLM |
| Verification | O(m/b) | Parallel batch processing |
| Fixing | O(k/b) | k = inaccurate faults |
| Consolidation | O(m log m) | Sort by timestamp |

### Space Complexity

- **Memory**: O(n + m) for DataFrames
- **Cache**: O(200) API responses
- **Disk**: O(output files) CSVs

### Bottlenecks

1. **LLM Calls**: Primary bottleneck (network + inference time)
2. **API Rate Limits**: JLab API may throttle requests
3. **ChromaDB Search**: Vector similarity computation

### Optimization Strategies

1. **Increase batch sizes**: Fewer LLM calls
2. **Increase workers**: More parallelism
3. **Cache warming**: Pre-fetch common data
4. **Selective processing**: Filter halls/date ranges

---

## Extension Points

### Adding New Pipeline Stages

```python
# 1. Create new module in analysis/
def new_stage(input_df, agent, max_workers, batch_size):
    # Process
    return output_df

# 2. Add to pipeline.py
from analysis.new_module import new_stage

def run_pipeline(...):
    # ... existing stages ...
    result = new_stage(result, agent, max_workers, batch_size)
    # ... continue ...
```

### Adding New Tags

1. Edit `tag_db/tags.json`
2. Add new tag with name, keywords, description
3. ChromaDB auto-rebuilds on next run

### Custom LLM Agents

```bash
# Set different agent
./scripts/run_pipeline.sh --agent custom_analyst

# Or in .env
AGENT_NAME=custom_analyst
```

---

*For detailed module documentation, see [MODULES.md](./MODULES.md).*
