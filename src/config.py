"""
Centralized configuration management for CLAW-Agent.
Replaces hardcoded values and credentials with environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import List

# Load environment variables from .env file if it exists
load_dotenv()

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
SRC_DIR = BASE_DIR / "src"

# Data paths
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FINAL_OUTPUT_DIR = DATA_DIR / "final_output"
VERIFIED_DIR = DATA_DIR / "verified"
FIXED_DIR = DATA_DIR / "fixed"

# File paths
SHIFT_SUMMARY_JSON = RAW_DIR / "shift_summary.JSON"
SHIFT_SUMMARY_CSV = RAW_DIR / "shift_summary.csv"
PROCESSED_SUMMARIES_CSV = PROCESSED_DIR / "processed_summaries.csv"
ALL_FAULTS_CSV = FINAL_OUTPUT_DIR / "all_shift_faults.csv"
NOT_FAULTS_CSV = PROCESSED_DIR / "not_faults.csv"
ACCURATE_CSV = VERIFIED_DIR / "accurate.csv"
INACCURATE_CSV = VERIFIED_DIR / "inaccurate.csv"
FIXED_CSV = FIXED_DIR / "fixed.csv"
MANUAL_CHECK_CSV = FINAL_OUTPUT_DIR / "manual_check.csv"

# API Configuration
JLAB_LOGBOOK_BASE_URL = "https://logbooks.jlab.org/api/elog"

# Hall to logbook ID mapping
HALL_LOGBOOKS = {
    "hall_a": "halog",      # Main Hall A Operational Logbook
    "hall_b": "hblog",      # Main Hall B Operational Logbook  
    "hall_c": "hclog",      # Main Hall C Operational Logbook
    "hall_d": "hdlog",      # Main Hall D Operational Logbook
}

# Default: all halls
DEFAULT_HALLS = list(HALL_LOGBOOKS.keys())
EXCLUDED_LOGBOOKS = ["-3", "-5"]
SEARCH_TITLE = "Shift Summary"
DEFAULT_PAGE_LIMIT = 50
API_DELAY_SECONDS = 0.5

# Authentication - Use environment variables or fallback to prompts
JLAB_USERNAME = os.getenv("JLAB_USERNAME", None)
JLAB_PASSWORD = os.getenv("JLAB_PASSWORD", None)

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Single agent for all pipeline stages
AGENT_NAME = os.getenv("AGENT_NAME", "fault_analyst")

# OpenClaw Configuration
# If OPENCLAW_PATH is set, use it to construct the OpenClaw command
# If not set, the project will use vLLM API directly
OPENCLAW_PATH = os.getenv("OPENCLAW_PATH", None)

if OPENCLAW_PATH:
    # Use OpenClaw installation path
    OPENCLAW_CMD = OPENCLAW_PATH
    USE_VLLM_DIRECTLY = False
else:
    # No OpenClaw path set - use vLLM API directly
    OPENCLAW_CMD = None
    USE_VLLM_DIRECTLY = True

# vLLM Configuration (used when OPENCLAW_PATH is not set)
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000")
VLLM_MODEL_NAME = os.getenv("VLLM_MODEL_NAME", "qwen3-32b")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", None)

# SSH Tunnel Configuration
# Dynamically loads SSH_TUNNEL_N_LOCAL and SSH_TUNNEL_N_REMOTE pairs
SSH_USERNAME = os.getenv("SSH_USERNAME", None)
SSH_HOST = os.getenv("SSH_HOST", None)

# SSH Port Conflict Behavior
# If true: Force-close any processes using the configured tunnel ports before establishing the tunnel
# If false: Skip tunnel creation if ports are already in use (pipeline continues without tunneling)
SSH_FORCE_CLOSE_PORTS = os.getenv("SSH_FORCE_CLOSE_PORTS", "true").lower() == "true"

def _parse_ssh_tunnels() -> list:
    """
    Parse SSH tunnel pairs from environment variables.
    Supports SSH_TUNNEL_N_LOCAL and SSH_TUNNEL_N_REMOTE for N=1,2,3...
    Returns a list of (local_port, remote_port) tuples.
    """
    tunnels = []
    n = 1
    while True:
        local_key = f"SSH_TUNNEL_{n}_LOCAL"
        remote_key = f"SSH_TUNNEL_{n}_REMOTE"
        
        local_port = os.getenv(local_key)
        remote_port = os.getenv(remote_key)
        
        if local_port is None and remote_port is None:
            # No more tunnels defined
            break
        
        if local_port is None or remote_port is None:
            # Incomplete pair - warn and skip
            import warnings
            warnings.warn(f"Incomplete SSH tunnel configuration for pair {n}: "
                         f"{local_key}={local_port}, {remote_key}={remote_port}")
            n += 1
            continue
        
        try:
            tunnels.append((int(local_port), int(remote_port)))
        except ValueError:
            import warnings
            warnings.warn(f"Invalid port numbers for SSH tunnel {n}: "
                         f"{local_key}={local_port}, {remote_key}={remote_port}")
        
        n += 1
    
    return tunnels

SSH_TUNNELS = _parse_ssh_tunnels()

# Verification thresholds
TIMESTAMP_TOLERANCE_MINUTES = 15

# Ensure all directories exist
for dir_path in [RAW_DIR, PROCESSED_DIR, FINAL_OUTPUT_DIR, VERIFIED_DIR, FIXED_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


def validate_config() -> List[str]:
    """
    Validate configuration values and return a list of warnings/errors.
    
    Returns:
        List of validation messages (empty if all valid)
    """
    issues = []
    
    # Check base directories
    if not BASE_DIR.exists():
        issues.append(f"ERROR: Base directory does not exist: {BASE_DIR}")
    
    # Check data directories
    for dir_name, dir_path in [
        ("raw", RAW_DIR),
        ("processed", PROCESSED_DIR),
        ("final_output", FINAL_OUTPUT_DIR),
        ("verified", VERIFIED_DIR),
        ("fixed", FIXED_DIR)
    ]:
        if not dir_path.exists():
            issues.append(f"WARNING: {dir_name} directory does not exist and will be created: {dir_path}")
        elif not os.access(dir_path, os.W_OK):
            issues.append(f"ERROR: No write permission for {dir_name} directory: {dir_path}")
    
    # Check required JLab credentials
    if JLAB_USERNAME is None or JLAB_USERNAME.strip() == "":
        issues.append("ERROR: JLAB_USERNAME is not set. Please set it in .env file.")
    if JLAB_PASSWORD is None or JLAB_PASSWORD.strip() == "":
        issues.append("ERROR: JLAB_PASSWORD is not set. Please set it in .env file.")
    
    # Check LOG_LEVEL
    if LOG_LEVEL is None or LOG_LEVEL.strip() == "":
        issues.append("ERROR: LOG_LEVEL is not set. Please set it in .env file (e.g., INFO, DEBUG, WARNING).")
    elif LOG_LEVEL.upper() not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        issues.append(f"WARNING: LOG_LEVEL '{LOG_LEVEL}' may be invalid. Expected: DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
    
    # Check LLM configuration: either (AGENT_NAME + OPENCLAW_PATH) OR (VLLM_BASE_URL + VLLM_MODEL_NAME)
    has_openclaw = AGENT_NAME and OPENCLAW_CMD
    has_vllm = VLLM_BASE_URL and VLLM_MODEL_NAME
    
    if not has_openclaw and not has_vllm:
        issues.append("ERROR: LLM configuration missing. You must provide EITHER:")
        issues.append("  - AGENT_NAME and OPENCLAW_PATH (for OpenClaw CLI mode), OR")
        issues.append("  - VLLM_BASE_URL and VLLM_MODEL_NAME (for direct vLLM API mode)")
    elif has_openclaw and has_vllm:
        # Both modes configured - prefer OpenClaw if OPENCLAW_PATH is set
        issues.append("WARNING: Both OpenClaw and vLLM configurations are set. Using OpenClaw CLI mode.")
    elif has_vllm and not has_openclaw:
        # vLLM mode only
        if not VLLM_BASE_URL:
            issues.append("ERROR: VLLM_BASE_URL is not set (required for vLLM mode).")
        if not VLLM_MODEL_NAME:
            issues.append("ERROR: VLLM_MODEL_NAME is not set (required for vLLM mode).")
    elif has_openclaw and not has_vllm:
        # OpenClaw mode only
        if not AGENT_NAME:
            issues.append("ERROR: AGENT_NAME is not set (required for OpenClaw mode).")
        if not OPENCLAW_CMD:
            issues.append("ERROR: OPENCLAW_PATH is not set (required for OpenClaw mode).")
    
    # Check agent configuration (for OpenClaw mode)
    if AGENT_NAME is None or AGENT_NAME.strip() == "":
        if OPENCLAW_CMD:  # Only error if using OpenClaw mode
            issues.append("ERROR: AGENT_NAME is empty or not set (required for OpenClaw CLI mode).")
    
    # Check SSH tunnel configuration (only if SSH_USERNAME is set)
    if SSH_USERNAME and not SSH_HOST:
        issues.append("ERROR: SSH_USERNAME is set but SSH_HOST is not configured.")
    if SSH_HOST and not SSH_USERNAME:
        issues.append("ERROR: SSH_HOST is set but SSH_USERNAME is not configured.")
    
    # Check if tunnels are configured when SSH is enabled
    if SSH_USERNAME and SSH_HOST and not SSH_TUNNELS:
        issues.append("WARNING: SSH credentials configured but no tunnels defined. "
                     "Add SSH_TUNNEL_N_LOCAL and SSH_TUNNEL_N_REMOTE pairs if tunneling is needed.")
    
    # Check API configuration
    if not JLAB_LOGBOOK_BASE_URL:
        issues.append("ERROR: JLAB_LOGBOOK_BASE_URL is not set.")
    elif not JLAB_LOGBOOK_BASE_URL.startswith("https://"):
        issues.append(f"WARNING: JLAB_LOGBOOK_BASE_URL should use HTTPS: {JLAB_LOGBOOK_BASE_URL}")
    
    # Check numeric parameters
    if DEFAULT_PAGE_LIMIT <= 0:
        issues.append(f"ERROR: DEFAULT_PAGE_LIMIT must be positive: {DEFAULT_PAGE_LIMIT}")
    
    if API_DELAY_SECONDS < 0:
        issues.append(f"ERROR: API_DELAY_SECONDS cannot be negative: {API_DELAY_SECONDS}")
    
    if TIMESTAMP_TOLERANCE_MINUTES <= 0:
        issues.append(f"ERROR: TIMESTAMP_TOLERANCE_MINUTES must be positive: {TIMESTAMP_TOLERANCE_MINUTES}")
    
    # Check hall configuration
    if not HALL_LOGBOOKS:
        issues.append("ERROR: HALL_LOGBOOKS is empty.")
    
    if not DEFAULT_HALLS:
        issues.append("ERROR: DEFAULT_HALLS is empty.")
    
    return issues


def validate_config_strict() -> bool:
    """
    Validate configuration and raise an error if any critical issues are found.
    
    Returns:
        True if validation passes
        
    Raises:
        ValueError: If critical configuration issues are found
    """
    issues = validate_config()
    errors = [msg for msg in issues if msg.startswith("ERROR")]
    
    if errors:
        error_msg = "\n".join(["\n" + "="*60, "CONFIGURATION VALIDATION FAILED:", "="*60, ""] + errors + ["", "Please fix the above errors in your .env file before running the pipeline.", "="*60 + "\n"])
        raise ValueError(error_msg)
    
    # Print warnings
    warnings = [msg for msg in issues if msg.startswith("WARNING")]
    if warnings:
        print("\n" + "="*60)
        print("CONFIGURATION WARNINGS:")
        print("="*60)
        for warning in warnings:
            print(f"  {warning}")
        print("="*60 + "\n")
    
    return True
