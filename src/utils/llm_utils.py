"""
Optimized LLM interaction utilities.
Uses openclaw agent subprocess calls OR vLLM API directly depending on configuration.
"""
import subprocess
import json
import uuid
import time
import requests
from typing import Optional, List, Dict, Any

from config import (
    AGENT_NAME, OPENCLAW_CMD, USE_VLLM_DIRECTLY,
    VLLM_BASE_URL, VLLM_MODEL_NAME, VLLM_API_KEY
)
from utils.logging_utils import logger
from utils.shutdown import is_shutdown_requested


# Prompt templates - centralized to avoid duplication
PROMPT_TEMPLATES = {
    "fault_extraction": """
Extract any and all faults (errors, crashes, delays, etc.) from the following shift summary.

Format each fault as a JSON object with these fields:
- timestamp: time in HH:MM 24-hour format (e.g., "20:05") - REQUIRED
- description: brief description of the fault - REQUIRED
- run_number: run number if mentioned - OPTIONAL (omit if not present)

CRITICAL TIMESTAMP RULES:
1. ONLY extract timestamps in the correct format.
2. Acceptable formats: "14:30", "2:30 PM", "1430", "02:30pm"
3. DO NOT create faults in the time format:
   - Vague ("around", "approximately", "before", "after", "during")
   - Relative ("45min into run", "1hr into run", "last 2 hours")
   - Unknown ("N/A", "unspecified", "unknown", "before start")
   - A time range ("17:00-18:20")

IMPORTANT:
- Every fault MUST have timestamp and description fields
- run_number MUST be a STRING (e.g., "12345" not 12345) - wrap in quotes!
- Return ONLY a JSON array of fault objects, nothing else
- Do NOT include any explanation or schema definition
- If no faults exist, return empty array []

Example output format:
[
  {"timestamp": "08:15", "description": "RF system trip", "run_number": "12345"},
  {"timestamp": "14:30", "description": "Cooling failure"}
]

Shift Summary:
{shift_summary}
""",
    "tagger_prompt": """
You are classifying a fault from a Jefferson Lab shift summary log.

You have been given a fault description and a list of candidate tags retrieved from a knowledge base.
Choose the single most appropriate tag for this fault.
If none of the candidates clearly fit, respond with: Other

Fault description: {description}

Candidate tags: {tag_options}

Respond with only the tag name, exactly as written above. No explanation.
""",
    
    "timestamp_verification": """
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
""",
    
    "timestamp_correction": """
You are a precise data extraction assistant. Return ONLY a timestamp.

CONTEXT:
- Fault description: {description}

FULL LOGBOOK ENTRY (source of truth):
{logbook}

TASK:
Extract the CORRECT timestamp for this fault from the logbook.
Output ONLY the timestamp in HH:MM 24-hour format (e.g., "14:30").
No punctuation, no explanation, no extra text.
""",
    
    "fault_validation": """
You are a fault validation system. Output ONLY "Yes" or "No".

TASK: Determine if this log entry describes a valid fault/event:
- YES if it describes: fault, error, crash, delay, alarm, trip, reboot, failure, issue, problem, shutdown
- NO if it describes: routine operations, normal status updates, informational notes, trivia, jokes

LOG ENTRY: {description}

OUTPUT:
- "Yes" if it is a valid fault/event
- "No" if it is NOT a fault/event

Output ONLY the word "Yes" or "No". No punctuation, no explanation.
""",
    "fault_extraction_batch": """
Extract faults from these shift summaries. Return ONLY a JSON array.

Each element must have:
- "source_index": integer (0, 1, 2...) matching the summary order
- "faults": array of fault objects with timestamp, description, and optional run_number

CRITICAL TIMESTAMP RULES:
1. ONLY extract faults in the correct format
2. Acceptable formats: "14:30", "2:30 PM", "1430", "02:30pm"
3. DO NOT create faults in the time format:
   - Vague ("around", "approximately", "before", "after", "during")
   - Relative ("45min into run", "1hr into run", "last 2 hours")
   - Unknown ("N/A", "unspecified", "unknown", "before start")
   - A time range ("17:00-18:20")

IMPORTANT:
- Every fault MUST have timestamp and description fields
- run_number MUST be a STRING (e.g., "12345" not 12345)
- Return ONLY a JSON array, nothing else
- Do NOT include any explanation

Example output format:
[
  {"source_index": 0, "faults": [{"timestamp": "08:15", "description": "RF trip", "run_number": "12345"}]},
  {"source_index": 1, "faults": []}
]

{summaries_block}
""",
    "tagger_batch": """
Classify these faults. Return ONLY a JSON array.

Each element must have:
- "index": integer matching the fault order below (0, 1, 2...)
- "tag": selected tag name

Candidate tags: {tag_options}

Faults:
{faults_block}
""",
    "fault_validation_batch": """
Determine which entries are valid faults. Return ONLY a JSON array.

Each element must have:
- "index": integer matching the fault order below (0, 1, 2...)
- "valid": "Yes" if it is a valid fault, "No" if it is NOT a valid fault

TASK: A valid fault describes: error, crash, delay, alarm, trip, reboot, failure, issue, problem, shutdown
An invalid entry describes: routine operations, normal status updates, informational notes, trivia, jokes

Faults to validate:
{faults_block}
""",
    "timestamp_verification_batch": """
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
""",
    "timestamp_correction_batch": """
Extract the correct timestamp for each fault from the logbook entry. Return ONLY a JSON array.

Each element must have:
- "index": integer matching the fault order below (0, 1, 2...)
- "timestamp": the correct time in HH:MM format, or "24:00" for midnight (00:00 next day)

TASK: Find the exact time mentioned in the logbook that matches each fault description.
- Look for time patterns like "14:30", "2:30 PM", "1430", "2:30"
- If the fault occurred at midnight, return "24:00" (caller will handle date rollover)
- If you cannot find a matching timestamp, return ""

Logbook Entry:
{logbook_content}

Faults to fix:
{faults_block}
"""
}


def call_llm(
    prompt: str, 
    agent: str = None,
    timeout_seconds: int = 30000,
    max_retries: int = 3,
    retry_delay: float = 2.0
) -> Optional[str]:
    """
    Call LLM using either openclaw agent subprocess OR vLLM API directly.
    
    Args:
        prompt: User prompt
        agent: openclaw agent name (ignored when using vLLM directly)
        timeout_seconds: Timeout in seconds (default: 300)
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Base delay between retries in seconds (default: 2.0)
        
    Returns:
        LLM response content or None after all retries exhausted or shutdown requested
    """
    # Route to appropriate implementation based on configuration
    if USE_VLLM_DIRECTLY:
        return _call_vllm(prompt, timeout_seconds, max_retries, retry_delay)
    else:
        return _call_openclaw(prompt, agent, timeout_seconds, max_retries, retry_delay)


def _call_openclaw(
    prompt: str,
    agent: str,
    timeout_seconds: int,
    max_retries: int,
    retry_delay: float
) -> Optional[str]:
    """
    Call LLM using openclaw agent subprocess with retry logic.
    """
    if agent is None:
        agent = AGENT_NAME
    
    # Check if OPENCLAW_CMD is set
    if not OPENCLAW_CMD:
        logger.error("OPENCLAW_CMD is not set and USE_VLLM_DIRECTLY is False. Cannot call openclaw.")
        return None
    
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        # Check for shutdown before each attempt
        if is_shutdown_requested():
            logger.info("LLM call aborted due to shutdown request")
            return None
        
        try:
            session_key = f"run-{uuid.uuid4()}"
            
            result = subprocess.run(
                [OPENCLAW_CMD, "agent", "--agent", agent, 
                 "--session-key", session_key, "--message", prompt],
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            
            if result.returncode == 0:
                if attempt > 1:
                    logger.info(f"LLM call succeeded on attempt {attempt}/{max_retries}")
                return result.stdout
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                last_error = f"Subprocess error (exit code {result.returncode}): {error_msg}"
                logger.warning(f"LLM call attempt {attempt}/{max_retries} failed: {last_error}")
            
        except subprocess.TimeoutExpired:
            last_error = f"Timeout after {timeout_seconds} seconds"
            logger.warning(f"LLM call attempt {attempt}/{max_retries} timed out: {last_error}")
        except FileNotFoundError as e:
            logger.error(f"openclaw command not found: {e}")
            return None
        except Exception as e:
            last_error = str(e)
            logger.warning(f"LLM call attempt {attempt}/{max_retries} failed with exception: {last_error}")
        
        # If not the last attempt, wait before retrying (interruptible)
        if attempt < max_retries:
            # Check for shutdown during retry wait
            if is_shutdown_requested():
                logger.info("LLM retry aborted due to shutdown request")
                return None
            
            # Exponential backoff: delay * 2^(attempt-1)
            wait_time = retry_delay * (2 ** (attempt - 1))
            logger.info(f"Retrying in {wait_time:.1f} seconds...")
            
            # Wait in small increments to check for shutdown
            elapsed = 0
            increment = 0.5  # Check every 500ms
            while elapsed < wait_time:
                if is_shutdown_requested():
                    logger.info("LLM retry interrupted due to shutdown request")
                    return None
                time.sleep(min(increment, wait_time - elapsed))
                elapsed += increment
    
    # All retries exhausted
    logger.error(f"LLM call failed after {max_retries} attempts. Last error: {last_error}")
    return None


def _call_vllm(
    prompt: str,
    timeout_seconds: int,
    max_retries: int,
    retry_delay: float
) -> Optional[str]:
    """
    Call LLM using vLLM API directly with retry logic.
    
    Args:
        prompt: User prompt
        timeout_seconds: Timeout in seconds
        max_retries: Maximum retry attempts
        retry_delay: Base delay between retries
        
    Returns:
        LLM response content or None
    """
    # Validate vLLM configuration
    if not VLLM_BASE_URL:
        logger.error("VLLM_BASE_URL is not set. Cannot call vLLM API.")
        return None
    
    url = f"{VLLM_BASE_URL}/v1/chat/completions"
    
    # Build headers
    headers = {"Content-Type": "application/json"}
    if VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {VLLM_API_KEY}"
    
    # Build request payload
    payload = {
        "model": VLLM_MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 120000,
        "stream": False
    }
    
    # DEBUG: Log request details
    logger.debug(f"vLLM REQUEST URL: {url}")
    logger.debug(f"vLLM REQUEST MODEL: {VLLM_MODEL_NAME}")
    logger.debug(f"vLLM REQUEST PAYLOAD (truncated): {str(payload)[:500]}...")
    logger.debug(f"vLLM REQUEST PROMPT LENGTH: {len(prompt)} chars")
    
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        # Check for shutdown before each attempt
        if is_shutdown_requested():
            logger.info("vLLM call aborted due to shutdown request")
            return None
        
        try:
            logger.debug(f"vLLM API call attempt {attempt}/{max_retries}...")
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds
            )
            
            # DEBUG: Log response details
            logger.debug(f"vLLM RESPONSE STATUS CODE: {response.status_code}")
            logger.debug(f"vLLM RESPONSE HEADERS: {dict(response.headers)}")
            logger.debug(f"vLLM RESPONSE BODY (first 1000 chars): {response.text[:1000]}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    logger.debug(f"vLLM RESPONSE JSON keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
                    if "choices" in result and len(result["choices"]) > 0:
                        choice = result["choices"][0]
                        logger.debug(f"vLLM RESPONSE CHOICE keys: {choice.keys() if isinstance(choice, dict) else 'not a dict'}")
                        
                        message = choice.get("message", {})
                        logger.debug(f"vLLM RESPONSE MESSAGE: {message}")
                        
                        content = message.get("content") if isinstance(message, dict) else None
                        logger.debug(f"vLLM RESPONSE CONTENT value: {content}")
                        
                        if content is not None:
                            logger.debug(f"vLLM RESPONSE CONTENT LENGTH: {len(content)} chars")
                            logger.debug(f"vLLM RESPONSE CONTENT (first 200 chars): {content[:200]}")
                            if attempt > 1:
                                logger.info(f"vLLM call succeeded on attempt {attempt}/{max_retries}")
                            return content
                        else:
                            # Fallback: Check reasoning field (some models put output there)
                            reasoning = message.get("reasoning") if isinstance(message, dict) else None
                            logger.debug(f"vLLM RESPONSE REASONING value: {reasoning}")
                            
                            if reasoning is not None:
                                logger.warning(f"vLLM returned reasoning instead of content. Using reasoning field.")
                                logger.debug(f"vLLM REASONING LENGTH: {len(reasoning)} chars")
                                logger.debug(f"vLLM REASONING (first 200 chars): {reasoning[:200]}")
                                if attempt > 1:
                                    logger.info(f"vLLM call succeeded on attempt {attempt}/{max_retries} (reasoning fallback)")
                                return reasoning
                            else:
                                last_error = "Content field is None in response"
                                logger.error(f"vLLM call attempt {attempt}/{max_retries} failed: {last_error}")
                                logger.error(f"vLLM full response JSON: {result}")
                    else:
                        last_error = "No choices in response"
                        logger.warning(f"vLLM call attempt {attempt}/{max_retries} failed: {last_error}")
                        logger.warning(f"vLLM full response JSON: {result}")
                except json.JSONDecodeError as e:
                    last_error = f"JSON decode error: {e}"
                    logger.error(f"vLLM response is not valid JSON: {last_error}")
                    logger.error(f"vLLM raw response: {response.text[:500]}")
            else:
                error_msg = response.text.strip() if response.text else f"HTTP {response.status_code}"
                last_error = f"HTTP error {response.status_code}: {error_msg}"
                logger.warning(f"vLLM call attempt {attempt}/{max_retries} failed: {last_error}")
            
        except requests.exceptions.Timeout:
            last_error = f"Timeout after {timeout_seconds} seconds"
            logger.error(f"vLLM call attempt {attempt}/{max_retries} timed out: {last_error}")
            logger.error(f"vLLM TIMEOUT - Check if vLLM server is running at {VLLM_BASE_URL}")
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {str(e)}"
            logger.error(f"vLLM call attempt {attempt}/{max_retries} failed: {last_error}")
            logger.error(f"vLLM CONNECTION ERROR - Check if vLLM server is running at {VLLM_BASE_URL}")
            logger.error(f"vLLM Try: curl -v {VLLM_BASE_URL}/v1/models")
        except Exception as e:
            last_error = str(e)
            logger.error(f"vLLM call attempt {attempt}/{max_retries} failed with exception: {last_error}")
            import traceback
            logger.error(f"vLLM EXCEPTION TRACEBACK: {traceback.format_exc()}")
        
        # If not the last attempt, wait before retrying (interruptible)
        if attempt < max_retries:
            # Check for shutdown during retry wait
            if is_shutdown_requested():
                logger.info("vLLM retry aborted due to shutdown request")
                return None
            
            # Exponential backoff: delay * 2^(attempt-1)
            wait_time = retry_delay * (2 ** (attempt - 1))
            logger.info(f"Retrying in {wait_time:.1f} seconds...")
            
            # Wait in small increments to check for shutdown
            elapsed = 0
            increment = 0.5  # Check every 500ms
            while elapsed < wait_time:
                if is_shutdown_requested():
                    logger.info("vLLM retry interrupted due to shutdown request")
                    return None
                time.sleep(min(increment, wait_time - elapsed))
                elapsed += increment
    
    # All retries exhausted
    logger.error(f"vLLM call failed after {max_retries} attempts. Last error: {last_error}")
    return None
