# Shutdown Utilities

Documentation for graceful shutdown handling in CLAW-Agent.

---

## Overview

The shutdown module provides **thread-safe graceful shutdown management** for the entire application. It uses a global `threading.Event` to signal shutdown across all worker threads, with custom SIGINT handling for Ctrl+C interrupts.

**Module**: `src/utils/shutdown.py`

**Key Features**:
- Thread-safe shutdown flag via `threading.Event`
- Custom SIGINT (Ctrl+C) handler for graceful shutdown
- Interruptible wait operations
- Programmatic shutdown control
- Force-exit protection (prevents hanging)

---

## Core Components

### Global Shutdown Event

```python
_shutdown_event = threading.Event()
```

**Type**: `threading.Event`

**Purpose**: Thread-safe flag for signaling shutdown across all threads

**Behavior**:
- **Set** by SIGINT signal handler (Ctrl+C)
- **Set** programmatically via `request_shutdown()`
- **Cleared** via `clear_shutdown()` (testing only)
- **Non-blocking check** via `is_shutdown_requested()`
- **Blocking wait** via `wait_for_shutdown(timeout)`

**Thread Safety**: `threading.Event` is inherently thread-safe for all operations

---

## Functions

### `setup_shutdown_handler()`

Registers the SIGINT (Ctrl+C) signal handler for graceful shutdown.

**Signature**:
```python
def setup_shutdown_handler() -> None
```

**When to Call**: **At the very start** of the main process, before any worker threads are created.

**Example**:
```python
from utils.shutdown import setup_shutdown_handler

# Must be called first
setup_shutdown_handler()

# Now safe to start workers
main()
```

**What It Does**:

1. **Registers SIGINT handler**: Intercepts Ctrl+C
2. **Sets shutdown event**: Signals all threads to stop
3. **Prints message**: Informs user of graceful shutdown
4. **Starts force-exit thread**: Prevents hanging if workers don't respond

**Signal Handler Behavior**:

```python
def signal_handler(signum, frame):
    _shutdown_event.set()
    print("\nShutdown requested (Ctrl+C). Waiting for workers to finish current task...")
    
    # Start force-exit thread (prevents hanging)
    def force_exit():
        import time
        time.sleep(0.5)
        if not _shutdown_event.is_set():
            print("Force exiting...")
            sys.exit(130)
    
    threading.Thread(target=force_exit, daemon=True).start()
```

**Force-Exit Thread**:
- Waits 0.5 seconds after shutdown request
- If shutdown event is **not** set (unexpected), force exits
- Runs as daemon thread (doesn't block process exit)
- **Note**: The condition `if not _shutdown_event.is_set()` appears to be a safeguard against an edge case where the signal handler might not have properly set the event

**Exit Codes**:
- **Normal exit**: 0
- **Graceful shutdown**: 0 (after workers finish)
- **Force exit**: 130 (SIGINT exit code)

**Important**: Only handles **SIGINT** (Ctrl+C). SIGTERM (kill command) uses default behavior (immediate termination).

---

### `is_shutdown_requested() -> bool`

Non-blocking check if shutdown has been requested.

**Signature**:
```python
def is_shutdown_requested() -> bool
```

**Returns**: `True` if shutdown event is set, `False` otherwise

**Performance**: O(1) - just checks internal flag

**Example**:
```python
from utils.shutdown import is_shutdown_requested

# In worker loop
for item in items:
    if is_shutdown_requested():
        logger.info("Shutdown requested, stopping...")
        break
    
    process(item)
```

**Usage Pattern**:

**Before long operations**:
```python
if is_shutdown_requested():
    return None  # Skip work

result = expensive_operation(item)
```

**During long operations** (check periodically):
```python
for i in range(1000):
    if is_shutdown_requested():
        break
    
    do_small_task(i)
```

**After operations** (before starting next):
```python
result = process(item)

if is_shutdown_requested():
    return None  # Don't continue

save_result(result)
```

**Best Practices**:
- Check **before** starting long operations
- Check **during** long operations (every few iterations)
- Check **after** operations (before starting next)
- Don't check too frequently (unnecessary overhead)

---

### `wait_for_shutdown(timeout: float = None) -> bool`

Block until shutdown is requested or timeout expires.

**Signature**:
```python
def wait_for_shutdown(timeout: float = None) -> bool
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timeout` | float | `None` | Max wait time in seconds (None = wait forever) |

**Returns**: `True` if shutdown requested, `False` if timeout expired

**Example**:

```python
from utils.shutdown import wait_for_shutdown

# Wait indefinitely until shutdown
wait_for_shutdown()
print("Shutdown requested")

# Wait up to 5 seconds
if wait_for_shutdown(timeout=5):
    print("Shutdown requested")
else:
    print("Timeout expired, continuing...")
```

**Use Cases**:

1. **Idle worker waiting**:
   ```python
   while True:
       if wait_for_shutdown(timeout=60):
           break
       # Check for new work
   ```

2. **Polling with timeout**:
   ```python
   while not is_shutdown_requested():
       # Wait up to 10 seconds for shutdown
       wait_for_shutdown(timeout=10)
       
       # Check for new work
       if has_work():
           process_work()
   ```

3. **Batch processing with shutdown check**:
   ```python
   for batch in batches:
       # Wait for shutdown before starting batch
       if wait_for_shutdown(timeout=1):
           break
       
       process_batch(batch)
   ```

**Timeout Behavior**:
- `timeout=None`: Block forever until shutdown
- `timeout=0`: Non-blocking check (returns immediately)
- `timeout=5.0`: Block up to 5 seconds

**Return Values**:
- `True`: Shutdown event was set (user requested shutdown)
- `False`: Timeout expired (shutdown not requested)

---

### `request_shutdown()`

Programmatically request shutdown (equivalent to Ctrl+C).

**Signature**:
```python
def request_shutdown() -> None
```

**Example**:
```python
from utils.shutdown import request_shutdown

# Request shutdown from code
if critical_error:
    logger.error("Critical error, requesting shutdown")
    request_shutdown()
    return  # Current function exits

# Main loop will detect and exit
```

**Use Cases**:
- **Critical errors**: Stop all processing on unrecoverable error
- **External trigger**: Shutdown triggered by external condition
- **Testing**: Simulate Ctrl+C in unit tests
- **Cleanup**: Request shutdown before cleanup operations

**Behavior**:
- Sets the global shutdown event
- **Does NOT** print message (unlike Ctrl+C)
- **Does NOT** start force-exit thread
- All threads checking `is_shutdown_requested()` will see it immediately

---

### `clear_shutdown()`

Clear the shutdown flag (reset to not-requested state).

**Signature**:
```python
def clear_shutdown() -> None
```

**Example**:
```python
from utils.shutdown import clear_shutdown

# Clear shutdown flag
clear_shutdown()

# Now is_shutdown_requested() returns False
```

**Warning**: **Use only for testing or recovery**, not in production code.

**Use Cases**:
- **Unit testing**: Reset state between test cases
- **Recovery**: Rare cases where shutdown was requested in error
- **Development**: Debugging shutdown behavior

**Never Use In Production**:
```python
# BAD: Clearing shutdown in production code
while True:
    if is_shutdown_requested():
        clear_shutdown()  # Never do this!
        continue
```

**Safe Testing Example**:
```python
def test_worker_respects_shutdown():
    from utils.shutdown import request_shutdown, clear_shutdown, is_shutdown_requested
    
    # Reset state
    clear_shutdown()
    assert is_shutdown_requested() == False
    
    # Request shutdown
    request_shutdown()
    assert is_shutdown_requested() == True
    
    # Cleanup for next test
    clear_shutdown()
```

---

## Signal Handling

### SIGINT (Ctrl+C)

**Handler**: Custom handler registered by `setup_shutdown_handler()`

**Trigger**: User presses Ctrl+C in terminal

**Handler Flow**:

```
User presses Ctrl+C
       │
       ▼
signal_handler(signum=2, frame) called
       │
       ▼
_shutdown_event.set()
       │
       ▼
Print: "Shutdown requested (Ctrl+C). Waiting for workers..."
       │
       ▼
Start force_exit thread (daemon, 0.5s delay)
       │
       ▼
Signal handler returns (process continues)
       │
       ▼
Worker threads detect shutdown_event.is_set()
       │
       ▼
Workers exit gracefully
       │
       ▼
Main loop detects shutdown_event.is_set()
       │
       ▼
Main loop exits
       │
       ▼
Process exits cleanly (exit code 0)
```

**Force-Exit Thread**:
```python
def force_exit():
    time.sleep(0.5)
    if not _shutdown_event.is_set():
        print("Force exiting...")
        sys.exit(130)
```

**Purpose**: Prevents process from hanging indefinitely if workers don't respond to shutdown.

**Note**: The condition `if not _shutdown_event.is_set()` is unusual - it would force exit if the event is NOT set after 0.5s, which shouldn't happen since the signal handler sets it immediately. This may be a safeguard against an edge case or a bug in the original implementation.

### SIGTERM (kill command)

**Handler**: **Not explicitly handled**

**Behavior**: Default SIGTERM behavior (immediate termination)

**Exit Code**: 143 (128 + 15, where 15 is SIGTERM)

**Implication**: If you send `kill <pid>`, the process terminates immediately without graceful shutdown.

**To Handle SIGTERM** (not implemented):
```python
# Add to setup_shutdown_handler():
signal.signal(signal.SIGTERM, signal_handler)  # Same handler as SIGINT
```

---

## Usage Patterns

### Worker Thread Pattern

```python
from utils.shutdown import is_shutdown_requested
from concurrent.futures import ThreadPoolExecutor

def worker(item):
    """Worker that respects shutdown."""
    # Check before starting
    if is_shutdown_requested():
        return None
    
    # Process item
    result = process_item(item)
    
    # Check before returning
    if is_shutdown_requested():
        return None  # Don't save result
    
    return result

# Parallel processing with shutdown support
setup_shutdown_handler()

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(worker, item) for item in items]
    
    for future in as_completed(futures):
        # Check shutdown between completions
        if is_shutdown_requested():
            logger.info("Shutdown requested, stopping...")
            executor.shutdown(wait=False)  # Don't wait for remaining
            break
        
        result = future.result()
        if result is not None:
            save_result(result)
```

### Main Loop Pattern

```python
from utils.shutdown import setup_shutdown_handler, is_shutdown_requested

setup_shutdown_handler()

# Main processing loop
for batch in batches:
    if is_shutdown_requested():
        logger.info("Shutdown requested, finishing current batch...")
        break
    
    process_batch(batch)
    logger.info(f"Batch {batch.id} complete")

logger.info("Shutdown complete")
```

### Long Operation Pattern

```python
from utils.shutdown import is_shutdown_requested

def long_operation(items):
    """Operation that takes a long time."""
    results = []
    
    for i, item in enumerate(items):
        # Check every 100 items
        if i % 100 == 0 and is_shutdown_requested():
            logger.info(f"Shutdown requested at item {i}")
            break
        
        result = expensive_process(item)
        results.append(result)
    
    return results
```

### Polling Pattern

```python
from utils.shutdown import wait_for_shutdown

def polling_worker():
    """Worker that polls for work."""
    while True:
        # Wait for shutdown or timeout
        if wait_for_shutdown(timeout=10):
            logger.info("Shutdown requested, exiting poll loop")
            break
        
        # Check for new work
        work = check_for_work()
        if work:
            process_work(work)
```

### Interruptible Sleep Pattern

```python
from utils.shutdown import is_shutdown_requested
import time

def interruptible_sleep(duration):
    """Sleep that can be interrupted by shutdown."""
    elapsed = 0
    increment = 0.5  # Check every 500ms
    
    while elapsed < duration:
        if is_shutdown_requested():
            logger.info("Sleep interrupted by shutdown")
            return
        
        time.sleep(min(increment, duration - elapsed))
        elapsed += increment
```

**Usage in LLM calls** (see `UTILS_LLM.md`):
```python
# Wait with shutdown check during retry
wait_time = 4.0
elapsed = 0
increment = 0.5

while elapsed < wait_time:
    if is_shutdown_requested():
        return None
    time.sleep(min(increment, wait_time - elapsed))
    elapsed += increment
```

---

## Graceful Shutdown Flow

### Complete Shutdown Sequence

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User presses Ctrl+C                                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. signal_handler(signum=2, frame) called                   │
│    - _shutdown_event.set()                                  │
│    - Print: "Shutdown requested (Ctrl+C)..."                │
│    - Start force_exit thread (daemon, 0.5s)                 │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
┌───────────────────────┐     ┌───────────────────────┐
│ 3a. Worker threads    │     │ 3b. Main loop         │
│     detect event      │     │     detects event     │
└───────────────────────┘     └───────────────────────┘
            │                               │
            ▼                               ▼
┌───────────────────────┐     ┌───────────────────────┐
│ 4a. Finish current    │     │ 4b. Stop processing   │
│     task, exit        │     │     current batch     │
└───────────────────────┘     └───────────────────────┘
            │                               │
            └───────────────┬───────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. All threads exit cleanly                                 │
│    - No orphaned threads                                    │
│    - No incomplete writes                                   │
│    - Resources released                                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Process exits with code 0                                │
└─────────────────────────────────────────────────────────────┘
```

### Force-Exit Scenario

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User presses Ctrl+C                                      │
│    - Shutdown event set                                     │
│    - force_exit thread started (0.5s delay)                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Workers not responding (stuck in long operation)         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. force_exit thread wakes after 0.5s                       │
│    - Checks: if not _shutdown_event.is_set()                │
│    - If true: sys.exit(130)                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Process exits immediately (exit code 130)                │
│    - Workers may be killed mid-operation                    │
│    - May leave incomplete work                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing

### Unit Test: Basic Shutdown Detection

```python
import pytest
from utils.shutdown import request_shutdown, clear_shutdown, is_shutdown_requested

def test_shutdown_requested():
    """Test shutdown flag is set correctly."""
    # Reset state
    clear_shutdown()
    assert is_shutdown_requested() == False
    
    # Request shutdown
    request_shutdown()
    assert is_shutdown_requested() == True
    
    # Cleanup
    clear_shutdown()
```

### Unit Test: Worker Respects Shutdown

```python
from utils.shutdown import request_shutdown, clear_shutdown, is_shutdown_requested
import time

def test_worker_exits_on_shutdown():
    """Test worker thread exits when shutdown requested."""
    from threading import Thread
    
    clear_shutdown()
    
    exit_count = 0
    
    def worker():
        nonlocal exit_count
        for i in range(1000):
            if is_shutdown_requested():
                exit_count += 1
                return
            time.sleep(0.001)
    
    # Start worker
    t = Thread(target=worker)
    t.start()
    
    # Let it run a bit
    time.sleep(0.1)
    
    # Request shutdown
    request_shutdown()
    
    # Wait for thread
    t.join(timeout=1.0)
    
    assert t.is_alive() == False  # Thread should have exited
    assert exit_count == 1  # Should have exited once
    
    clear_shutdown()
```

### Unit Test: Interruptible Sleep

```python
def test_interruptible_sleep():
    """Test sleep can be interrupted."""
    from utils.shutdown import request_shutdown, clear_shutdown, is_shutdown_requested
    import time
    
    clear_shutdown()
    
    start = time.time()
    
    # Start shutdown request in background
    def request_after_delay():
        time.sleep(0.2)
        request_shutdown()
    
    Thread(target=request_after_delay).start()
    
    # Sleep for 10 seconds (should be interrupted)
    elapsed = 0
    increment = 0.05
    
    while elapsed < 10:
        if is_shutdown_requested():
            break
        time.sleep(min(increment, 10 - elapsed))
        elapsed += increment
    
    duration = time.time() - start
    
    # Should have exited after ~0.2s, not 10s
    assert duration < 1.0  # Exited early
    assert duration > 0.1  # But not instantly
    
    clear_shutdown()
```

### Manual Testing

```bash
# Test graceful shutdown
cd CLAW-Agent
python3 -c "
from utils.shutdown import setup_shutdown_handler, is_shutdown_requested
import time

setup_shutdown_handler()

print('Press Ctrl+C to test graceful shutdown...')
for i in range(100):
    if is_shutdown_requested():
        print(f'Shutdown detected at iteration {i}')
        break
    time.sleep(0.1)

print('Shutdown complete')
"
# Press Ctrl+C after a few seconds
```

---

## Troubleshooting

### Ctrl+C Terminates Immediately

**Symptom**: Process exits immediately on Ctrl+C, no graceful shutdown

**Cause**: `setup_shutdown_handler()` not called

**Fix**:
```python
# Add at the very start of main()
from utils.shutdown import setup_shutdown_handler
setup_shutdown_handler()
```

### Workers Don't Stop After Ctrl+C

**Symptom**: Ctrl+C pressed, but workers continue running

**Cause**: Workers not checking `is_shutdown_requested()`

**Fix**:
```python
# Add shutdown checks in worker loop
for item in items:
    if is_shutdown_requested():
        break  # Exit loop
    process(item)
```

### Process Hangs After Ctrl+C

**Symptom**: Ctrl+C pressed, process doesn't exit even after long time

**Possible Causes**:

1. **Worker stuck in non-interruptible operation**:
   ```python
   # Bad: Long blocking operation without checks
   time.sleep(300)  # Can't interrupt
   
   # Good: Interruptible sleep
   for _ in range(600):
       if is_shutdown_requested():
           break
       time.sleep(0.5)
   ```

2. **Worker waiting on I/O**:
   ```python
   # Bad: Blocking I/O without timeout
   data = socket.recv()  # Blocks forever
   
   # Good: Non-blocking or timeout
   socket.settimeout(5.0)
   try:
       data = socket.recv()
   except socket.timeout:
       if is_shutdown_requested():
           return
   ```

3. **Thread not daemonized and main exits**:
   ```python
   # Bad: Non-daemon thread keeps process alive
   t = Thread(target=worker)  # Default daemon=False
   t.start()
   
   # Good: Daemon thread exits with main
   t = Thread(target=worker, daemon=True)
   t.start()
   ```

**Force Exit**: If process hangs, the force-exit thread will terminate it after 0.5s (if condition is met).

### Shutdown Event Set But Not Detected

**Symptom**: `request_shutdown()` called, but workers don't see it

**Cause**: Workers checking wrong variable or not importing correctly

**Debug**:
```python
from utils.shutdown import is_shutdown_requested, _shutdown_event

print(f"Event set: {_shutdown_event.is_set()}")
print(f"Function returns: {is_shutdown_requested()}")
```

**Fix**: Ensure all workers import from same module:
```python
# All workers should use:
from utils.shutdown import is_shutdown_requested

# NOT:
from utils import shutdown
shutdown.is_shutdown_requested()  # May not work if imported differently
```

### Force-Exit Thread Not Working

**Symptom**: Process hangs indefinitely after Ctrl+C

**Possible Cause**: Force-exit thread condition is `if not _shutdown_event.is_set()`, which may never be true since the signal handler sets the event immediately.

**Workaround**: Increase force-exit timeout or manually kill process.

**Note**: This appears to be a potential bug in the original implementation. The force-exit logic may need revision.

---

## Performance Characteristics

### Overhead

**`is_shutdown_requested()`**: O(1) - just checks internal flag, negligible overhead

**`wait_for_shutdown()`**: Uses OS-level condition variable, efficient blocking

**`request_shutdown()`**: O(1) - just sets event flag

### Memory Usage

**Per Process**: ~1KB (Event object + signal handler)

**Impact**: Negligible

---

## Related Documentation

- [LLM Utilities](./UTILS_LLM.md) - Shutdown in LLM calls (interruptible retries)
- [Architecture](../pipeline/ARCHITECTURE.md) - System shutdown design
- [Operations](../pipeline/OPERATIONS_PIPELINE.md) - Interrupt handling in production

---

*For LLM shutdown integration details, see [UTILS_LLM.md](./UTILS_LLM.md).*
