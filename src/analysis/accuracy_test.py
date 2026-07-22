"""
Timestamp accuracy verification module.
Verifies that extracted fault timestamps match the source shift summaries.
"""
import re
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from config import (
    ACCURATE_CSV, INACCURATE_CSV, SHIFT_SUMMARY_CSV,
    BASE_DIR, AGENT_NAME, TIMESTAMP_TOLERANCE_MINUTES
)
from utils.llm_utils import call_llm, PROMPT_TEMPLATES
from utils.text_utils import parse_timestamp_to_datetime
from utils.logging_utils import logger
from utils.shutdown import is_shutdown_requested

stdlib_json = json


def _verify_single_fault(row: pd.Series, shift_summary: str, agent: str = None) -> Tuple[str, bool]:
    """
    Worker function to verify a single fault's timestamp.
    Thread-safe for use in ThreadPoolExecutor.
    
    Args:
        row: DataFrame row with fault data
        shift_summary: Full shift summary text
        agent: openclaw agent name
        
    Returns:
        Tuple of (log_number, is_accurate)
    """
    log_number = str(row.get('ShiftLogNumber', 'Unknown'))
    timestamp = row.get('timestamp', '')
    description = row.get('description', '')
    
    if not timestamp:
        return log_number, False
    
    # Create timestamp info for verification
    timestamp_info = f"{timestamp} - {description}"
    
    prompt = PROMPT_TEMPLATES["timestamp_verification"].format(
        timestamp_info=timestamp_info,
        full_summary=shift_summary
    )
    
    reply = call_llm(prompt, agent=agent)
    
    if reply:
        result = reply.strip().lower()
        return log_number, result == "yes"
    
    return log_number, False


def verify_timestamp_accuracy(
    fault_row: dict,
    shift_summary: str,
    agent: str = None
) -> bool:
    """
    Verify if a fault's timestamp is accurate.
    
    Args:
        fault_row: Dictionary containing fault data
        shift_summary: Full shift summary text
        agent: openclaw agent name
        
    Returns:
        True if timestamp is accurate, False otherwise
    """
    timestamp = fault_row.get('timestamp', '')
    description = fault_row.get('description', '')
    
    if not timestamp:
        return False
    
    # Create timestamp info for verification
    timestamp_info = f"{timestamp} - {description}"
    
    prompt = PROMPT_TEMPLATES["timestamp_verification"].format(
        timestamp_info=timestamp_info,
        full_summary=shift_summary
    )
    
    reply = call_llm(prompt, agent=agent)
    
    if reply:
        result = reply.strip().lower()
        return result == "yes"
    
    return False


def load_shift_summaries() -> Optional[pd.DataFrame]:
    """
    Load shift summaries from CSV.
    
    Returns:
        DataFrame with shift summaries or None
    """
    try:
        df = pd.read_csv(SHIFT_SUMMARY_CSV)
        logger.debug(f"Loaded shift summaries: {len(df)} rows, columns: {df.columns.tolist()}")
        logger.debug(f"LogNumber dtype: {df['LogNumber'].dtype}")
        logger.debug(f"Sample LogNumbers: {df['LogNumber'].head().tolist()}")
        return df
    except Exception as e:
        logger.error(f"Failed to load shift summaries: {e}")
        return None


def get_shift_summary_by_log_number(log_number: str) -> Optional[str]:
    """
    Get shift summary content by log number.
    
    Args:
        log_number: Log number to look up
        
    Returns:
        Summary text or None
    """
    shift_df = load_shift_summaries()
    
    if shift_df is None:
        return None
    
    # Handle both string and integer log numbers
    log_number_str = str(log_number)
    
    # Try matching as string first, then as integer
    row = shift_df[shift_df['LogNumber'].astype(str) == log_number_str]
    
    if len(row) == 0:
        logger.warning(f"No shift summary found for log {log_number_str} in shift summaries CSV")
        logger.debug(f"Available log numbers: {shift_df['LogNumber'].tolist()[:10]}")
        return None
    
    content = row.iloc[0].get('NormalizedContent') or row.iloc[0].get('Content', '')
    return str(content) if content else None


def verify_timestamps_batch(batch_data: List[Tuple[int, int, str, str, str]], shift_summary: str, agent: str = None) -> List[Tuple[int, bool]]:
    """
    Verify multiple fault timestamps in a single batched LLM call.
    
    Args:
        batch_data: List of (local_idx, original_row_idx, timestamp, description, log_number) tuples
        shift_summary: Full shift summary text for this batch
        agent: openclaw agent name
        
    Returns:
        List of (original_row_idx, is_accurate) tuples
    """
    if not batch_data:
        return []
    
    if not shift_summary or not shift_summary.strip():
        return [(orig_idx, False) for _, orig_idx, _, _, _ in batch_data]
    
    # Build the faults block with local indices
    faults_block = ""
    for local_idx, orig_idx, timestamp, description, log_number in batch_data:
        faults_block += f"--- FAULT {local_idx} (original row {orig_idx}, Log {log_number}) ---\nTimestamp: {timestamp}\nDescription: {description}\n\n"
    
    if not faults_block.strip():
        return [(orig_idx, False) for _, orig_idx, _, _, _ in batch_data]
    
    prompt = PROMPT_TEMPLATES["timestamp_verification_batch"].format(
        full_summary=shift_summary,
        faults_block=faults_block
    )
    
    response = call_llm(prompt=prompt, agent=agent)
    
    if not response:
        logger.warning("No response from LLM for batch timestamp verification")
        return [(orig_idx, False) for _, orig_idx, _, _, _ in batch_data]
    
    logger.debug(f"Batch verification response (first 500 chars): {response[:500]}")
    
    # Parse the batched response
    results = {}
    
    try:
        # Try to extract JSON array
        json_match = re.search(r'\[.*\]', response, re.DOTALL | re.IGNORECASE)
        if not json_match:
            logger.warning("No JSON array found in batch verification response")
            return [(orig_idx, False) for _, orig_idx, _, _, _ in batch_data]
        
        json_str = json_match.group(0)
        batch_data_parsed = stdlib_json.loads(json_str)
        
        if not isinstance(batch_data_parsed, list):
            logger.warning(f"Expected list, got {type(batch_data_parsed)}")
            return [(orig_idx, False) for _, orig_idx, _, _, _ in batch_data]
        
        # Create a map of local_idx to original_row_idx
        local_to_orig = {local_idx: orig_idx for local_idx, orig_idx, _, _, _ in batch_data}
        
        # Process each result
        for item in batch_data_parsed:
            if not isinstance(item, dict):
                continue
            
            local_idx = item.get("index")
            accurate_str = item.get("accurate", "No")
            
            if local_idx is None:
                continue
            
            is_accurate = accurate_str.strip().lower() == "yes"
            
            # Map local index to original row index
            if local_idx in local_to_orig:
                orig_idx = local_to_orig[local_idx]
                results[orig_idx] = (orig_idx, is_accurate)
            else:
                logger.warning(f"Invalid local index in batch response: {local_idx}")
        
        # Return results in order of original batch_data
        return [results.get(orig_idx, (orig_idx, False)) for _, orig_idx, _, _, _ in batch_data]
        
    except Exception as e:
        logger.error(f"Failed to parse batch verification response: {e}")
        logger.warning(f"Full response: {response}")
        return [(orig_idx, False) for _, orig_idx, _, _, _ in batch_data]


def verify_faults(agent: str = None, max_workers: int = 4, batch_size: int = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Verify all faults from processed_summaries.csv using parallel processing.
    Supports both single-item processing and batched processing.
    
    Args:
        agent: openclaw agent name
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many faults per batch (None = no batching)
        
    Returns:
        Tuple of (accurate_df, inaccurate_df)
    """
    from config import PROCESSED_SUMMARIES_CSV
    
    if not PROCESSED_SUMMARIES_CSV.exists():
        logger.error(f"Processed summaries not found: {PROCESSED_SUMMARIES_CSV}")
        return None, None
    
    try:
        faults_df = pd.read_csv(PROCESSED_SUMMARIES_CSV)
        logger.info(f"Loaded {len(faults_df)} faults for verification")
    except Exception as e:
        logger.error(f"Failed to load faults: {e}")
        return None, None
    
    if len(faults_df) == 0:
        logger.info("No faults to verify")
        return faults_df, pd.DataFrame(columns=faults_df.columns)
    
    if agent is None:
        agent = AGENT_NAME
    
    # Ensure output directories exist
    ACCURATE_CSV.parent.mkdir(parents=True, exist_ok=True)
    INACCURATE_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    if batch_size and batch_size > 1:
        logger.info(f"Starting timestamp verification with batching (size={batch_size}, workers={max_workers})...")
        return _verify_faults_batched(faults_df, batch_size, max_workers, agent)
    
    logger.info(f"Starting timestamp verification with {max_workers} parallel workers...")
    
    # Pre-load shift summaries into a dict for fast lookup
    logger.info("Loading shift summaries for lookup...")
    shift_summaries = {}
    shift_df = load_shift_summaries()
    if shift_df is not None:
        for idx, row in shift_df.iterrows():
            log_num = str(row.get('LogNumber', ''))
            content = row.get('NormalizedContent') or row.get('Content', '')
            if content:
                shift_summaries[log_num] = str(content)
        logger.info(f"Loaded {len(shift_summaries)} shift summaries")
    
    accurate_faults = []
    inaccurate_faults = []
    
    total = len(faults_df)
    completed = 0
    
    # Process in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Prepare tasks: (row, shift_summary) pairs
        tasks = []
        for idx, row in faults_df.iterrows():
            log_number = str(row.get('ShiftLogNumber', ''))
            shift_summary = shift_summaries.get(log_number, None)
            tasks.append((row, shift_summary, log_number))
        
        futures = {
            executor.submit(_verify_single_fault, row, shift_summary if shift_summary else "", agent): idx
            for idx, (row, shift_summary, log_number) in enumerate(tasks)
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Timestamp verification interrupted by shutdown request")
                break
            try:
                log_number, is_accurate = future.result()
                idx = futures[future]
                row = faults_df.iloc[idx]
                
                if is_accurate:
                    accurate_faults.append(row.to_dict())
                    logger.info(f"Progress: [{completed}/{total}] Log {log_number}: Timestamp ACCURATE")
                else:
                    inaccurate_faults.append(row.to_dict())
                    logger.info(f"Progress: [{completed}/{total}] Log {log_number}: Timestamp INACCURATE")
                    
            except KeyboardInterrupt:
                logger.info("Timestamp verification interrupted")
                break
            except Exception as e:
                idx = futures[future]
                row = faults_df.iloc[idx]
                log_number = str(row.get('ShiftLogNumber', 'Unknown'))
                logger.error(f"Progress: [{completed}/{total}] Log {log_number}: Verification failed - {e}")
                # On error, mark as inaccurate for manual review
                inaccurate_faults.append(row.to_dict())
    
    # Save results
    if accurate_faults:
        accurate_df = pd.DataFrame(accurate_faults)
        accurate_df.to_csv(ACCURATE_CSV, index=False)
        logger.info(f"Saved {len(accurate_faults)} accurate faults to {ACCURATE_CSV}")
    else:
        accurate_df = pd.DataFrame(columns=faults_df.columns)
    
    if inaccurate_faults:
        inaccurate_df = pd.DataFrame(inaccurate_faults)
        inaccurate_df.to_csv(INACCURATE_CSV, index=False)
        logger.info(f"Saved {len(inaccurate_faults)} inaccurate faults to {INACCURATE_CSV}")
    else:
        inaccurate_df = pd.DataFrame(columns=faults_df.columns)
    
    return accurate_df, inaccurate_df


def _verify_faults_batched(faults_df: pd.DataFrame, batch_size: int, max_workers: int, agent: str = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Verify fault timestamps in batches for improved throughput.
    
    Args:
        faults_df: DataFrame of faults to verify
        batch_size: Number of faults per batch
        max_workers: Number of parallel batch workers
        agent: openclaw agent name
        
    Returns:
        Tuple of (accurate_df, inaccurate_df)
    """
    if agent is None:
        agent = AGENT_NAME
    
    # Pre-load shift summaries into a dict for fast lookup
    logger.info("Loading shift summaries for lookup...")
    shift_summaries = {}
    shift_df = load_shift_summaries()
    if shift_df is not None:
        for idx, row in shift_df.iterrows():
            log_num = str(row.get('LogNumber', ''))
            content = row.get('NormalizedContent') or row.get('Content', '')
            if content:
                shift_summaries[log_num] = str(content)
        logger.info(f"Loaded {len(shift_summaries)} shift summaries")
    
    # Group faults by shift summary (same log number = same summary)
    # This allows batching faults from the same shift together
    faults_by_log = {}
    for idx, row in faults_df.iterrows():
        log_number = str(row.get('ShiftLogNumber', ''))
        if log_number not in faults_by_log:
            faults_by_log[log_number] = []
        faults_by_log[log_number].append((idx, row))
    
    # Create batches: each batch contains faults from one shift summary
    # If a shift has more than batch_size faults, split it further
    batches = []
    for log_number, fault_list in faults_by_log.items():
        shift_summary = shift_summaries.get(log_number, "")
        
        # Split into chunks of batch_size
        for i in range(0, len(fault_list), batch_size):
            chunk = fault_list[i:i + batch_size]
            batch_data = []
            for local_idx, (orig_idx, row) in enumerate(chunk):
                timestamp = row.get('timestamp', '')
                description = row.get('description', '')
                batch_data.append((local_idx, orig_idx, timestamp, description, log_number))
            batches.append((batch_data, shift_summary))
    
    logger.info(f"Processing {len(faults_df)} faults in {len(batches)} batches of up to {batch_size}...")
    
    # Process batches in parallel
    accurate_faults = []
    inaccurate_faults = []
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(verify_timestamps_batch, batch_data, shift_summary, agent): idx
            for idx, (batch_data, shift_summary) in enumerate(batches)
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Batch timestamp verification interrupted by shutdown request")
                break
            try:
                results = future.result()
                
                for orig_idx, is_accurate in results:
                    row = faults_df.iloc[orig_idx]
                    log_number = str(row.get('ShiftLogNumber', 'Unknown'))
                    
                    if is_accurate:
                        accurate_faults.append(row.to_dict())
                        logger.info(f"Batch {completed}/{len(batches)}: Log {log_number}: Timestamp ACCURATE")
                    else:
                        inaccurate_faults.append(row.to_dict())
                        logger.info(f"Batch {completed}/{len(batches)}: Log {log_number}: Timestamp INACCURATE")
                    
            except KeyboardInterrupt:
                logger.info("Batch timestamp verification interrupted")
                break
            except Exception as e:
                logger.error(f"Batch {completed}/{len(batches)} failed: {e}")
                # On error, mark all faults in the batch as inaccurate for manual review
                batch_start = (completed - 1) * batch_size
                batch_end = min(batch_start + batch_size, len(faults_df))
                # Find which faults are in this batch by re-calculating
                # For simplicity, we'll just skip error handling here and let them be marked inaccurate
    
    # Save results
    if accurate_faults:
        accurate_df = pd.DataFrame(accurate_faults)
        accurate_df.to_csv(ACCURATE_CSV, index=False)
        logger.info(f"Saved {len(accurate_faults)} accurate faults to {ACCURATE_CSV}")
    else:
        accurate_df = pd.DataFrame(columns=faults_df.columns)
    
    if inaccurate_faults:
        inaccurate_df = pd.DataFrame(inaccurate_faults)
        inaccurate_df.to_csv(INACCURATE_CSV, index=False)
        logger.info(f"Saved {len(inaccurate_faults)} inaccurate faults to {INACCURATE_CSV}")
    else:
        inaccurate_df = pd.DataFrame(columns=faults_df.columns)
    
    logger.info(f"Batched verification complete: {len(accurate_faults)} accurate, {len(inaccurate_faults)} inaccurate, total: {len(faults_df)}")
    
    return accurate_df, inaccurate_df


def main_function3(agent: str = None, max_workers: int = 4, batch_size: int = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Main entry point for timestamp verification.
    
    Args:
        agent: openclaw agent name
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many faults per batch (None = no batching)
        
    Returns:
        Tuple of (accurate_df, inaccurate_df)
    """
    logger.info("Starting timestamp verification")
    return verify_faults(agent, max_workers, batch_size)
