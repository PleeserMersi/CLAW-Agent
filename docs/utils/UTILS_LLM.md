# LLM Utilities

Documentation for LLM interaction utilities. Uses OpenClaw CLI OR vLLM API directly depending on configuration.

---

## Overview

The LLM utilities module provides a **reliable interface** for calling LLMs via either OpenClaw CLI or vLLM API directly. It handles retry logic with exponential backoff, timeout management, graceful shutdown integration, and comprehensive error logging. It handles retry logic with exponential backoff, timeout management, graceful shutdown integration, and comprehensive error logging.

**Module**: `src/utils/llm_utils.py`

**Key Features**:
- LLM routing: OpenClaw CLI or vLLM API based on configuration
- Configurable timeout per attempt
- Exponential backoff retry strategy
- Graceful shutdown support (interruptible retry waits)
- Centralized prompt templates for all LLM operations
- Detailed logging for debugging and monitoring

---

## Core Function: `call_llm()`

### Signature

```python
def call_llm(
    prompt: str,
    agent: str = None,
    timeout_seconds: int = 300,
    max_retries: int = 3,
    retry_delay: float = 2.0
) -> Optional[str]
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | Required | User prompt to send to the LLM agent |
| `agent` | str | `None` | OpenClaw agent name (defaults to `AGENT_NAME` from config) |
| `timeout_seconds` | int | `300` | Timeout per attempt in seconds (5 minutes) |
| `max_retries` | int | `3` | Maximum number of retry attempts |
| `retry_delay` | float | `2.0` | Base delay between retries in seconds |

### Returns

- **Success**: LLM response as string (stdout from subprocess)
- **Failure**: `None` (after all retries exhausted or shutdown requested)

### Execution Flow

1. **Validate agent**: Use provided agent or fall back to `AGENT_NAME` from config
2. **Loop through attempts** (1 to `max_retries`):
   - Check for shutdown request → return `None` immediately
   - Generate unique `session_key` for this attempt
   - Execute `openclaw agent` subprocess with timeout
   - On success (exit code 0): return stdout
   - On failure: log warning, prepare for retry
   - If not last attempt: wait with exponential backoff (checking shutdown)
3. **All retries exhausted**: log error, return `None`

### Example Usage

```python
from utils.llm_utils import call_llm

# Basic usage (uses default agent from config)
response = call_llm(
    prompt="Extract faults from: 04:00 - RF trip detected"
)

# Custom agent and timeout
response = call_llm(
    prompt="Classify this fault: RF system error",
    agent="fault_analyst",
    timeout_seconds=600,
    max_retries=5
)

# Check result
if response:
    print(f"LLM response: {response}")
else:
    print("LLM call failed after all retries")
```

### Command Executed

The function executes this command:

```bash
openclaw agent --agent <agent_name> --session-key <uuid> --message "<prompt>"
```

**Example**:
```bash
openclaw agent --agent fault_analyst --session-key run-550e8400-e29b-41d4-a716-446655440000 --message "Extract faults..."
```

**Note**: Each attempt uses a **unique session key** (UUID v4) to ensure isolated agent sessions.

---

## Retry Logic

### Exponential Backoff Strategy

**Delay Calculation**:
```
Attempt 1: No delay (immediate)
Attempt 2: 2.0 seconds  (2.0 × 2^0)
Attempt 3: 4.0 seconds  (2.0 × 2^1)
Attempt 4: 8.0 seconds  (2.0 × 2^2)  [if max_retries >= 4]
```

**Formula**:
```python
wait_time = retry_delay * (2 ** (attempt - 1))
```

### Interruptible Retry Wait

Retry waits are **not blocking** - they check for shutdown every 500ms:

```python
elapsed = 0
increment = 0.5  # Check every 500ms
while elapsed < wait_time:
    if is_shutdown_requested():
        logger.info("LLM retry interrupted due to shutdown request")
        return None
    time.sleep(min(increment, wait_time - elapsed))
    elapsed += increment
```

**Why?**: Allows graceful shutdown even during long retry waits (e.g., 8-second wait on attempt 3).

### Retry Behavior by Error Type

| Error Type | Retry? | Reason |
|------------|--------|--------|
| `subprocess.TimeoutExpired` | ✅ Yes | Transient timeout, might succeed next time |
| Subprocess non-zero exit | ✅ Yes | Transient error, might be network/agent issue |
| `FileNotFoundError` (openclaw not found) | ❌ No | Permanent error, retry won't help |
| Shutdown requested | ❌ No | User requested stop, abort immediately |

### Sample Retry Log Output

```
[2026-07-17 10:15:00] [WARNING] LLM call attempt 1/3 failed: Subprocess error (exit code 1): Agent timeout
[2026-07-17 10:15:00] [INFO] Retrying in 2.0 seconds...
[2026-07-17 10:15:02] [WARNING] LLM call attempt 2/3 failed: Timeout after 300 seconds
[2026-07-17 10:15:02] [INFO] Retrying in 4.0 seconds...
[2026-07-17 10:15:06] [INFO] LLM call succeeded on attempt 3/3
```

---

## Prompt Templates

All LLM prompts are centralized in `PROMPT_TEMPLATES` dictionary for consistency and maintainability.

### Template Catalog

| Template Name | Purpose | Batch Support |
|---------------|---------|---------------|
| `fault_extraction` | Extract faults from single shift summary | ❌ No |
| `fault_extraction_batch` | Extract faults from multiple summaries | ✅ Yes |
| `tagger_prompt` | Classify single fault into tag category | ❌ No |
| `tagger_batch` | Classify multiple faults | ✅ Yes |
| `timestamp_verification` | Verify single timestamp accuracy | ❌ No |
| `timestamp_verification_batch` | Verify multiple timestamps | ✅ Yes |
| `timestamp_correction` | Extract correct timestamp for single fault | ❌ No |
| `timestamp_correction_batch` | Extract timestamps for multiple faults | ✅ Yes |
| `fault_validation` | Validate if single entry is a fault | ❌ No |
| `fault_validation_batch` | Validate multiple entries | ✅ Yes |

### Template Usage

```python
from utils.llm_utils import PROMPT_TEMPLATES, call_llm

# Single fault extraction
prompt = PROMPT_TEMPLATES["fault_extraction"].format(
    shift_summary="04:00 - RF issues detected during run 12345"
)
response = call_llm(prompt)

# Batch tagging
prompt = PROMPT_TEMPLATES["tagger_batch"].format(
    tag_options="Accelerator, Injector, Cryogenics",
    faults_block="""0: RF trip at 14:30
1: Cooling failure at 08:15
2: Vacuum alarm at 22:00"""
)
response = call_llm(prompt)
```

### Key Template Features

#### Fault Extraction Template

**Critical Rules**:
1. **Timestamp format enforcement**: Only accept `HH:MM`, `H:MM AM/PM`, `HHMM`, `H:MMam/pm`
2. **No vague timestamps**: Reject "around", "approximately", "before", "after"
3. **No relative timestamps**: Reject "45min into run", "1hr into run"
4. **No time ranges**: Reject "17:00-18:20" - skip these faults
5. **JSON-only output**: Return ONLY JSON array, no explanation
6. **String run numbers**: `"12345"` not `12345`

**Example Output**:
```json
[
  {"timestamp": "08:15", "description": "RF system trip", "run_number": "12345"},
  {"timestamp": "14:30", "description": "Cooling failure"}
]
```

#### Timestamp Verification Template

**Rules**:
1. Timestamp must exist in fault information
2. Must be within 15 minutes of time in shift summary
3. Output ONLY "Yes" or "No"

**Example**:
```
FAULT TIMESTAMP TO VERIFY:
14:30 - RF trip

FULL SHIFT SUMMARY:
04:00 - System startup
14:25 - RF trip detected
15:00 - System recovered

Output: Yes  (14:30 is within 15 min of 14:25)
```

#### Batch Templates

**Structure**:
- Each item has `source_index` or `index` (0-based)
- Returns JSON array with results in same order
- Enables parallel processing of multiple items

**Example Batch Input**:
```python
summaries_block = """
0: 04:00 - RF trip
1: 08:15 - Cooling failure
2: 14:30 - Vacuum alarm
"""

faults_block = """
0: RF trip at 14:30
1: Cooling failure at 08:15
2: Vacuum alarm at 22:00
"""
```

---

## Error Handling

### Timeout Errors

**Symptom**: `subprocess.TimeoutExpired`

**Log Output**:
```
[WARNING] LLM call attempt 1/3 timed out: Timeout after 300 seconds
```

**Handling**:
- Log warning with attempt number and timeout duration
- Retry with exponential backoff
- After all retries: log error, return `None`

**Mitigation**:
- Increase `timeout_seconds` for complex prompts
- Use batch processing to reduce total calls
- Check agent health before large runs

### Subprocess Errors

**Symptom**: Non-zero exit code from `openclaw agent`

**Log Output**:
```
[WARNING] LLM call attempt 1/3 failed: Subprocess error (exit code 1): Agent initialization failed
```

**Handling**:
- Extract stderr message for context
- Log warning with exit code and error message
- Retry with exponential backoff

**Common Causes**:
- Agent not configured (`AGENT_NAME` invalid)
- Ollama service down
- Network connectivity issues
- Invalid prompt syntax

### File Not Found

**Symptom**: `openclaw` command not in PATH

**Log Output**:
```
[ERROR] openclaw command not found: [Errno 2] No such file or directory: 'openclaw'
```

**Handling**:
- Log error immediately
- **Do not retry** (permanent error)
- Return `None`

**Fix**:
```bash
# Install OpenClaw
pip install openclaw

# Or add to PATH
export PATH="$PATH:/home/user/.npm-global/bin"
```

### All Retries Exhausted

**Symptom**: All attempts fail

**Log Output**:
```
[ERROR] LLM call failed after 3 attempts. Last error: Timeout after 300 seconds
```

**Handling**:
- Log error with final error message
- Return `None` to caller
- Caller should handle `None` (skip item, log, or abort)

### Shutdown Requested

**Symptom**: User presses Ctrl+C or shutdown signal received

**Log Output**:
```
[INFO] LLM call aborted due to shutdown request
```

**Handling**:
- **Immediate abort** if detected before attempt
- **Interruptible wait** if detected during retry delay
- Return `None` without completing

**Why Important**: Prevents long-running LLM calls from blocking shutdown

---

## Shutdown Integration

### How It Works

The `call_llm()` function integrates with the global shutdown system via `is_shutdown_requested()`:

```python
from utils.shutdown import is_shutdown_requested
```

### Check Points

1. **Before each attempt**:
   ```python
   if is_shutdown_requested():
       logger.info("LLM call aborted due to shutdown request")
       return None
   ```

2. **During retry wait** (every 500ms):
   ```python
   while elapsed < wait_time:
       if is_shutdown_requested():
           logger.info("LLM retry interrupted due to shutdown request")
           return None
       time.sleep(0.5)
       elapsed += 0.5
   ```

### Graceful Shutdown Flow

```
User presses Ctrl+C
    ↓
shutdown_event.set()
    ↓
is_shutdown_requested() returns True
    ↓
call_llm() detects and returns None immediately
    ↓
Pipeline stage receives None, handles gracefully
    ↓
Pipeline stage returns, cleanup occurs
    ↓
Application exits cleanly
```

---

## Performance Characteristics

### Typical Latencies

| Operation | Avg Time | Range |
|-----------|----------|-------|
| Simple prompt (validation) | 5-10s | 3-15s |
| Medium prompt (extraction) | 10-30s | 5-45s |
| Complex prompt (batch extraction) | 20-60s | 15-90s |

**Factors affecting latency**:
- LLM model speed (Ollama vs remote)
- Prompt complexity and length
- Response length
- Network latency (if remote)
- Agent initialization time

### Timeout Recommendations

| Operation | Recommended Timeout | Rationale |
|-----------|---------------------|-----------|
| Single fault extraction | 300s (5 min) | Usually completes in 10-30s |
| Batch extraction (10 items) | 600s (10 min) | May take 30-60s per item |
| Single tag classification | 120s (2 min) | Simple classification, fast |
| Batch tagging (20 items) | 300s (5 min) | Multiple classifications |
| Timestamp verification | 120s (2 min) | Simple Yes/No response |
| Complex analysis | 900s (15 min) | Multi-step reasoning |

### Retry Overhead

**Worst case** (all 3 retries fail):
```
Attempt 1: 300s (timeout) + 0s delay = 300s
Attempt 2: 300s (timeout) + 2s delay = 302s
Attempt 3: 300s (timeout) + 4s delay = 304s
Total: ~906s (15 minutes)
```

**Best case** (succeeds on attempt 1):
```
Attempt 1: 10s (actual) = 10s
```

**Average case** (succeeds on attempt 2 after timeout):
```
Attempt 1: 300s (timeout) + 2s delay = 302s
Attempt 2: 10s (actual) = 10s
Total: ~312s (5 minutes)
```

### Memory Usage

**Per Call**: ~50-100 MB (subprocess memory)

**Concurrent Calls**: Depends on pipeline batch size
- Extraction batch: 5 concurrent → ~500 MB
- Tagging batch: 10 concurrent → ~1 GB

---

## Configuration

### Environment Variables (from `.env`)

| Variable | Purpose | Example |
|----------|---------|---------|
| `AGENT_NAME` | Default agent for LLM calls | `fault_analyst` |
| `OPENCLAW_PATH` | OpenClaw installation path (enables openclaw CLI mode) | `/home/user/.npm-global/lib/node_modules/openclaw` |
| `VLLM_BASE_URL` | vLLM API endpoint (used when OPENCLAW_PATH not set) | `http://localhost:8000` |
| `VLLM_MODEL_NAME` | vLLM model name (used when OPENCLAW_PATH not set) | `qwen3-32b` |
| `VLLM_API_KEY` | vLLM API key (optional) | `sk-xxx` |

### Default Values

```python
# In config.py
AGENT_NAME = "fault_analyst"  # Must be configured in OpenClaw
OPENCLAW_CMD = "openclaw"      # Assumes in PATH
```

### Customizing Timeouts

```python
# In pipeline stage code
response = call_llm(
    prompt=prompt,
    timeout_seconds=600,  # Override default 300s
    max_retries=5,        # More retries for critical operations
    retry_delay=3.0       # Longer base delay
)
```

---

## Testing

### Unit Test: Basic Call

```python
import pytest
from unittest.mock import patch, MagicMock
from utils.llm_utils import call_llm

def test_call_llm_success():
    """Test successful LLM call."""
    with patch('utils.llm_utils.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"faults": []}',
            stderr=""
        )
        
        response = call_llm(
            prompt="Test prompt",
            agent="test_agent",
            timeout_seconds=60,
            max_retries=1
        )
        
        assert response == '{"faults": []}'
        mock_run.assert_called_once()

def test_call_llm_timeout_then_success():
    """Test retry after timeout."""
    with patch('utils.llm_utils.subprocess.run') as mock_run:
        # First call times out, second succeeds
        mock_run.side_effect = [
            subprocess.TimeoutExpired(cmd="openclaw", timeout=60),
            MagicMock(returncode=0, stdout="success", stderr="")
        ]
        
        response = call_llm(
            prompt="Test",
            max_retries=2,
            retry_delay=0.1  # Fast retry for testing
        )
        
        assert response == "success"
        assert mock_run.call_count == 2

def test_call_llm_all_retries_fail():
    """Test failure after all retries."""
    with patch('utils.llm_utils.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Agent error"
        )
        
        response = call_llm(
            prompt="Test",
            max_retries=2,
            retry_delay=0.1
        )
        
        assert response is None
        assert mock_run.call_count == 2

def test_call_llm_shutdown_interrupts():
    """Test shutdown during retry wait."""
    with patch('utils.llm_utils.subprocess.run') as mock_run:
        with patch('utils.llm_utils.is_shutdown_requested') as mock_shutdown:
            # First attempt fails, shutdown requested during retry
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Error"
            )
            mock_shutdown.side_effect = [False, True]  # False on attempt 1, True during wait
            
            response = call_llm(
                prompt="Test",
                max_retries=3,
                retry_delay=10.0  # Long delay to allow interrupt
            )
            
            assert response is None
            assert mock_run.call_count == 1  # Only 1 attempt before shutdown
```

### Manual Testing

```bash
# Test basic call
cd /home/sec-researchonly/Desktop/CLAW-Agent
python3 -c "
from utils.llm_utils import call_llm
response = call_llm('Hello, what is 2+2?', timeout_seconds=60)
print(f'Response: {response}')
"
```

---

## Troubleshooting

### "openclaw command not found"

**Symptom**:
```
[ERROR] openclaw command not found: [Errno 2] No such file or directory: 'openclaw'
```

**Cause**: OpenClaw not installed or not in PATH

**Fix**:
```bash
# Install OpenClaw
pip install openclaw

# Verify installation
which openclaw
openclaw --version

# If not in PATH, add to ~/.bashrc
echo 'export PATH="$PATH:/home/user/.npm-global/bin"' >> ~/.bashrc
source ~/.bashrc
```

### "Agent timeout" on every attempt

**Symptom**:
```
[WARNING] LLM call attempt 1/3 timed out: Timeout after 300 seconds
[WARNING] LLM call attempt 2/3 timed out: Timeout after 300 seconds
[WARNING] LLM call attempt 3/3 timed out: Timeout after 300 seconds
```

**Possible Causes**:

1. **Ollama service down**:
   ```bash
   # Check Ollama status
   curl http://localhost:11435/api/tags
   
   # Restart Ollama
   ollama serve
   ```

2. **Agent not configured**:
   ```bash
   # Check agent exists
   openclaw agent list
   
   # Configure agent
   openclaw agent configure fault_analyst
   ```

3. **Prompt too complex**:
   - Simplify prompt
   - Increase timeout
   - Use smaller batch sizes

**Fix**:
```python
# Increase timeout
response = call_llm(prompt, timeout_seconds=900)

# Reduce batch size
# Instead of 20 items, use 10
```

### "Subprocess error (exit code 1)"

**Symptom**:
```
[WARNING] LLM call attempt 1/3 failed: Subprocess error (exit code 1): Invalid agent name
```

**Cause**: Agent name in config doesn't exist

**Fix**:
```bash
# Check configured agents
openclaw agent list

# Update .env with correct agent name
AGENT_NAME=fault_analyst  # Must match agent name in OpenClaw
```

### Response is empty or malformed

**Symptom**:
```python
response = call_llm(prompt)
print(response)  # "" or garbled text
```

**Possible Causes**:

1. **Agent returned empty response**:
   - Check agent configuration
   - Verify prompt is valid

2. **JSON parsing failed**:
   - LLM didn't return valid JSON
   - Use stricter prompt instructions

**Debug**:
```python
response = call_llm(prompt)
if response:
    print(f"Raw response: {repr(response)}")
    try:
        data = json.loads(response)
        print(f"Parsed: {data}")
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
```

### Shutdown doesn't stop LLM calls

**Symptom**: Ctrl+C pressed but LLM call continues

**Cause**: Shutdown event not being checked

**Fix**: Ensure `is_shutdown_requested()` is called:
```python
# In calling code
from utils.shutdown import is_shutdown_requested

while processing_items:
    if is_shutdown_requested():
        break
    
    response = call_llm(prompt)
    # ... process response
```

---

## Related Documentation

- [Shutdown Utilities](./UTILS_SHUTDOWN.md) - Graceful interrupt handling
- [Configuration](../config/CONFIGURATION.md) - Agent and Ollama settings
- [Architecture](../pipeline/ARCHITECTURE.md) - LLM integration design
- [Fault Extraction](../pipeline/PIPELINE_FAULT_EXTRACTION.md) - Prompt usage example

---

*For shutdown handling details, see [UTILS_SHUTDOWN.md](./UTILS_SHUTDOWN.md).*