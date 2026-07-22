"""
Timestamp fixing module.
Corrects inaccurate timestamps by extracting the correct time from logbook entries.
"""
import re
import json
import csv
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd

from config import (
    FIXED_CSV, MANUAL_CHECK_CSV, INACCURATE_CSV,
    BASE_DIR, AGENT_NAME
)
from utils.llm_utils import call_llm, PROMPT_TEMPLATES
from utils.text_utils import normalize_timestamp, extract_time_from_text
from utils.logging_utils import logger
from utils.shutdown import is_shutdown_requested
from analysis.accuracy_test import verify_timestamps_batch

stdlib_json = json


def get_logbook_entry_by_log_number(log_number: str) -> Optional[str]:
    """
    Fetch full logbook entry content.
    
    Args:
        log_number: Log number to fetch
        
    Returns:
        Entry content or None
    """
    from utils.cache_utils import CachedAPIClient
    from config import JLAB_LOGBOOK_BASE_URL, JLAB_USERNAME, JLAB_PASSWORD
    
    api_client = CachedAPIClient(
        base_url=JLAB_LOGBOOK_BASE_URL,
        username=JLAB_USERNAME,
        password=JLAB_PASSWORD
    )
    
    entry = api_client.get_single_entry(log_number)
    
    if not entry:
        return None
    
    # Extract body content from the API response structure
    # Response format: {'stat': 'ok', 'data': {'entry': {'body': {'content': '...'}}}}
    data = entry.get('data', {})
    entry_data = data.get('entry', {})
    body = entry_data.get('body', {})
    content = body.get('content', '')
    
    return content if content else None


def _fix_single_timestamp(row: pd.Series, shift_summaries: Dict[str, str], agent: str = None) -> Tuple[str, dict, str]:
    """
    Worker function to fix a single fault's timestamp.
    Thread-safe for use in ThreadPoolExecutor.
    
    Args:
        row: DataFrame row with fault data
        shift_summaries: Dict mapping log_number to shift summary content
        agent: openclaw agent name
        
    Returns:
        Tuple of (log_number, updated_row_dict, status)
        status: 'fixed', 'low_confidence', or 'none'
    """
    log_number = str(row.get('ShiftLogNumber', 'Unknown'))
    description = row.get('description', '')
    
    if not log_number:
        return log_number, row.to_dict(), 'none'
    
    # Fetch full logbook entry
    logbook_content = get_logbook_entry_by_log_number(log_number)
    
    if not logbook_content:
        logger.warning(f"Could not fetch logbook {log_number}")
        return log_number, row.to_dict(), 'none'
    
    # Extract correct timestamp
    corrected_timestamp = extract_correct_timestamp(description, logbook_content, agent)
    
    if corrected_timestamp:
        # Update timestamp
        updated_row = row.to_dict()
        
        # Handle 24:00 case - need to update FullTimestamp with date rollover
        if corrected_timestamp == "24:00":
            # Parse the current FullTimestamp and add one day
            current_full_ts = row.get('FullTimestamp')
            if current_full_ts:
                try:
                    from datetime import timedelta
                    # Parse the current timestamp
                    if isinstance(current_full_ts, str):
                        current_dt = datetime.fromisoformat(current_full_ts.replace('Z', '+00:00'))
                    else:
                        current_dt = current_full_ts
                    # Add one day and set time to 00:00
                    new_dt = current_dt + timedelta(days=1)
                    new_dt = new_dt.replace(hour=0, minute=0)
                    updated_row['FullTimestamp'] = new_dt
                    updated_row['timestamp'] = "00:00"  # Store as 00:00 in CSV
                except Exception as e:
                    logger.warning(f"Failed to handle 24:00 date rollover: {e}")
                    updated_row['timestamp'] = "24:00"  # Keep as 24:00 for manual review
            else:
                updated_row['timestamp'] = "24:00"  # Keep as 24:00 for manual review
        else:
            updated_row['timestamp'] = corrected_timestamp
        
        # Re-verify the fix
        shift_summary = shift_summaries.get(log_number, None)
        if shift_summary:
            from analysis.accuracy_test import verify_timestamp_accuracy
            if verify_timestamp_accuracy(updated_row, shift_summary, agent):
                updated_row['fix_confidence'] = 'high'
                return log_number, updated_row, 'fixed'
        
        updated_row['fix_confidence'] = 'low'
        return log_number, updated_row, 'low_confidence'
    else:
        return log_number, row.to_dict(), 'none'


def extract_correct_timestamp(
    fault_description: str,
    logbook_content: str,
    agent: str = None
) -> Optional[str]:
    """
    Extract the correct timestamp for a fault from logbook content.
    
    Handles 24:00 by returning "24:00" (caller should handle date rollover).
    
    Args:
        fault_description: Fault description
        logbook_content: Full logbook entry content
        agent: openclaw agent name
        
    Returns:
        Corrected timestamp in HH:MM format, "24:00" for midnight rollover, or None
    """
    prompt = PROMPT_TEMPLATES["timestamp_correction"].format(
        description=fault_description,
        logbook=logbook_content
    )
    
    reply = call_llm(prompt, agent=agent)
    
    if reply:
        # Extract timestamp from response
        timestamp = normalize_timestamp(reply.strip())
        
        # Check if it's 24:00 case
        if timestamp is None:
            clean_reply = re.sub(r'[^0-9:]', '', reply.strip())
            if clean_reply == "24:00":
                return "24:00"
        
        return timestamp
    
    # Fallback: try to extract from text directly
    timestamp = extract_time_from_text(logbook_content)
    if timestamp:
        normalized = normalize_timestamp(timestamp)
        if normalized is None:
            clean_ts = re.sub(r'[^0-9:]', '', timestamp)
            if clean_ts == "24:00":
                return "24:00"
        return normalized
    
    return None


def fix_timestamps_batch(batch_data: List[Tuple[int, int, str, str]], logbook_content: str, agent: str = None) -> List[Tuple[int, str, str]]:
    """
    Fix multiple fault timestamps in a single batched LLM call.
    
    Args:
        batch_data: List of (local_idx, original_row_idx, description, log_number) tuples
        logbook_content: Full logbook entry content for this batch
        agent: openclaw agent name
        
    Returns:
        List of (original_row_idx, corrected_timestamp, status) tuples
        status: 'fixed' or 'none'
    """
    if not batch_data:
        return []
    
    if not logbook_content or not logbook_content.strip():
        return [(orig_idx, '', 'none') for _, orig_idx, _, _ in batch_data]
    
    # Build the faults block with local indices
    faults_block = ""
    for local_idx, orig_idx, description, log_number in batch_data:
        faults_block += f"--- FAULT {local_idx} (original row {orig_idx}, Log {log_number}) ---\nDescription: {description}\n\n"
    
    if not faults_block.strip():
        return [(orig_idx, '', 'none') for _, orig_idx, _, _ in batch_data]
    
    prompt = PROMPT_TEMPLATES["timestamp_correction_batch"].format(
        logbook_content=logbook_content,
        faults_block=faults_block
    )
    
    response = call_llm(prompt=prompt, agent=agent)
    
    if not response:
        logger.warning("No response from LLM for batch timestamp correction")
        return [(orig_idx, '', 'none') for _, orig_idx, _, _ in batch_data]
    
    logger.debug(f"Batch correction response (first 500 chars): {response[:500]}")
    
    # Parse the batched response
    results = {}
    
    try:
        # Try to extract JSON array
        json_match = re.search(r'\[.*\]', response, re.DOTALL | re.IGNORECASE)
        if not json_match:
            logger.warning("No JSON array found in batch correction response")
            return [(orig_idx, '', 'none') for _, orig_idx, _, _ in batch_data]
        
        json_str = json_match.group(0)
        batch_data_parsed = stdlib_json.loads(json_str)
        
        if not isinstance(batch_data_parsed, list):
            logger.warning(f"Expected list, got {type(batch_data_parsed)}")
            return [(orig_idx, '', 'none') for _, orig_idx, _, _ in batch_data]
        
        # Create a map of local_idx to original_row_idx
        local_to_orig = {local_idx: orig_idx for local_idx, orig_idx, _, _ in batch_data}
        
        # Process each result
        for item in batch_data_parsed:
            if not isinstance(item, dict):
                continue
            
            local_idx = item.get("index")
            timestamp = item.get("timestamp", "")
            
            if local_idx is None:
                continue
            
            # Normalize the timestamp
            if timestamp:
                normalized = normalize_timestamp(timestamp)
                if normalized is None:
                    # Check for 24:00 case
                    clean_ts = re.sub(r'[^0-9:]', '', timestamp)
                    if clean_ts == "24:00":
                        normalized = "24:00"
                    else:
                        normalized = timestamp  # Keep as-is if normalization fails
                timestamp = normalized
            
            # Map local index to original row index
            if local_idx in local_to_orig:
                orig_idx = local_to_orig[local_idx]
                status = 'fixed' if timestamp else 'none'
                results[orig_idx] = (orig_idx, timestamp, status)
            else:
                logger.warning(f"Invalid local index in batch response: {local_idx}")
        
        # Return results in order of original batch_data
        return [results.get(orig_idx, (orig_idx, '', 'none')) for _, orig_idx, _, _ in batch_data]
        
    except Exception as e:
        logger.error(f"Failed to parse batch correction response: {e}")
        logger.warning(f"Full response: {response}")
        return [(orig_idx, '', 'none') for _, orig_idx, _, _ in batch_data]


def fix_timestamps(agent: str = None, max_workers: int = 4, batch_size: int = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Fix timestamps for all inaccurate faults using parallel processing.
    Supports both single-item processing and batched processing.
    
    Args:
        agent: openclaw agent name
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many faults per batch (None = no batching)
        
    Returns:
        Tuple of (fixed_df, manual_check_df)
    """
    if not INACCURATE_CSV.exists():
        logger.warning(f"Inaccurate faults file not found: {INACCURATE_CSV}")
        return None, None
    
    try:
        inaccurate_df = pd.read_csv(INACCURATE_CSV)
        logger.info(f"Loaded {len(inaccurate_df)} inaccurate faults for fixing")
    except Exception as e:
        logger.error(f"Failed to load inaccurate faults: {e}")
        return None, None
    
    if len(inaccurate_df) == 0:
        logger.info("No inaccurate faults to fix")
        return pd.DataFrame(), pd.DataFrame()
    
    if agent is None:
        agent = AGENT_NAME
    
    # Ensure output directories exist
    FIXED_CSV.parent.mkdir(parents=True, exist_ok=True)
    MANUAL_CHECK_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    if batch_size and batch_size > 1:
        logger.info(f"Starting timestamp fixing with batching (size={batch_size}, workers={max_workers})...")
        return _fix_timestamps_batched(inaccurate_df, batch_size, max_workers, agent)
    
    logger.info(f"Starting timestamp fixing with {max_workers} parallel workers...")
    
    # Pre-load shift summaries into a dict for fast lookup
    logger.info("Loading shift summaries for verification...")
    shift_summaries = {}
    try:
        from config import SHIFT_SUMMARY_CSV
        shift_df = pd.read_csv(SHIFT_SUMMARY_CSV)
        for idx, row in shift_df.iterrows():
            log_num = str(row.get('LogNumber', ''))
            content = row.get('NormalizedContent') or row.get('Content', '')
            if content:
                shift_summaries[log_num] = str(content)
        logger.info(f"Loaded {len(shift_summaries)} shift summaries")
    except Exception as e:
        logger.warning(f"Could not load shift summaries: {e}")
    
    fixed_faults = []
    manual_check_faults = []
    
    total = len(inaccurate_df)
    completed = 0
    
    # Process in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_fix_single_timestamp, row, shift_summaries, agent): idx
            for idx, row in inaccurate_df.iterrows()
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Timestamp fixing interrupted by shutdown request")
                break
            try:
                log_number, updated_row, status = future.result()
                
                if status == 'fixed':
                    fixed_faults.append(updated_row)
                    logger.info(f"Progress: [{completed}/{total}] Log {log_number}: Fixed to {updated_row.get('timestamp')}")
                elif status == 'low_confidence':
                    manual_check_faults.append(updated_row)
                    logger.info(f"Progress: [{completed}/{total}] Log {log_number}: Fixed to {updated_row.get('timestamp')} (needs review)")
                else:
                    manual_check_faults.append(row.to_dict())
                    logger.info(f"Progress: [{completed}/{total}] Log {log_number}: Could not fix")
                    
            except KeyboardInterrupt:
                logger.info("Timestamp fixing interrupted")
                break
            except Exception as e:
                idx = futures[future]
                row = inaccurate_df.iloc[idx]
                log_number = str(row.get('ShiftLogNumber', 'Unknown'))
                logger.error(f"Progress: [{completed}/{total}] Log {log_number}: Fix failed - {e}")
                manual_check_faults.append(row.to_dict())
    
    # Save results
    if fixed_faults:
        fixed_df = pd.DataFrame(fixed_faults)
        fixed_df.to_csv(FIXED_CSV, index=False)
        logger.info(f"Saved {len(fixed_faults)} fixed faults to {FIXED_CSV}")
    else:
        fixed_df = pd.DataFrame(columns=inaccurate_df.columns) if inaccurate_df is not None else pd.DataFrame()
    
    if manual_check_faults:
        manual_df = pd.DataFrame(manual_check_faults)
        # Ensure only expected columns are written (remove fix_confidence and verification_status)
        expected_cols = [c for c in inaccurate_df.columns if c not in ('fix_confidence', 'verification_status')]
        manual_df = manual_df[[c for c in expected_cols if c in manual_df.columns]]
        # Append to existing manual_check.csv
        if MANUAL_CHECK_CSV.exists() and MANUAL_CHECK_CSV.stat().st_size > 0:
            manual_df.to_csv(MANUAL_CHECK_CSV, mode='a', index=False, header=False)
            logger.info(f"Appended {len(manual_check_faults)} faults needing manual review to {MANUAL_CHECK_CSV}")
        else:
            manual_df.to_csv(MANUAL_CHECK_CSV, mode='w', index=False, header=True)
            logger.info(f"Created {MANUAL_CHECK_CSV} with {len(manual_check_faults)} faults needing manual review")
    else:
        manual_df = pd.DataFrame(columns=inaccurate_df.columns) if inaccurate_df is not None else pd.DataFrame()
    
    return fixed_df, manual_df


def _fix_timestamps_batched(inaccurate_df: pd.DataFrame, batch_size: int, max_workers: int, agent: str = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Fix fault timestamps in batches for improved throughput.
    Also batches the re-verification step for additional speedup.
    
    Args:
        inaccurate_df: DataFrame of inaccurate faults to fix
        batch_size: Number of faults per batch (used for both fixing and re-verification)
        max_workers: Number of parallel batch workers
        agent: openclaw agent name
        
    Returns:
        Tuple of (fixed_df, manual_check_df)
    """
    if agent is None:
        agent = AGENT_NAME
    
    # Group faults by log number (same log = same logbook entry)
    faults_by_log = {}
    for idx, row in inaccurate_df.iterrows():
        log_number = str(row.get('ShiftLogNumber', ''))
        if log_number not in faults_by_log:
            faults_by_log[log_number] = []
        faults_by_log[log_number].append((idx, row))
    
    # Create batches: each batch contains faults from one logbook entry
    # If a log has more than batch_size faults, split it further
    batches = []
    for log_number, fault_list in faults_by_log.items():
        # Split into chunks of batch_size
        for i in range(0, len(fault_list), batch_size):
            chunk = fault_list[i:i + batch_size]
            batch_data = []
            for local_idx, (orig_idx, row) in enumerate(chunk):
                description = row.get('description', '')
                batch_data.append((local_idx, orig_idx, description, log_number))
            batches.append((batch_data, log_number))
    
    logger.info(f"Processing {len(inaccurate_df)} faults in {len(batches)} batches of up to {batch_size}...")
    
    # Process batches in parallel
    fixed_candidates = []  # Store (orig_idx, timestamp, row) for re-verification
    manual_check_faults = []
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_logbook_batch, batch_data, log_number, agent): idx
            for idx, (batch_data, log_number) in enumerate(batches)
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Batch timestamp fixing interrupted by shutdown request")
                break
            try:
                results = future.result()
                
                for orig_idx, timestamp, status in results:
                    row = inaccurate_df.iloc[orig_idx]
                    log_number = str(row.get('ShiftLogNumber', 'Unknown'))
                    
                    if status == 'fixed' and timestamp:
                        # Update the row with the corrected timestamp
                        updated_row = row.to_dict()
                        
                        # Handle 24:00 case - need to update FullTimestamp with date rollover
                        if timestamp == "24:00":
                            current_full_ts = row.get('FullTimestamp')
                            if current_full_ts:
                                try:
                                    if isinstance(current_full_ts, str):
                                        current_dt = datetime.fromisoformat(current_full_ts.replace('Z', '+00:00'))
                                    else:
                                        current_dt = current_full_ts
                                    new_dt = current_dt + timedelta(days=1)
                                    new_dt = new_dt.replace(hour=0, minute=0)
                                    updated_row['FullTimestamp'] = new_dt
                                    updated_row['timestamp'] = "00:00"
                                except Exception as e:
                                    logger.warning(f"Failed to handle 24:00 date rollover: {e}")
                                    updated_row['timestamp'] = "24:00"
                            else:
                                updated_row['timestamp'] = "24:00"
                        else:
                            updated_row['timestamp'] = timestamp
                        
                        # Add to candidates for batched re-verification
                        fixed_candidates.append((orig_idx, log_number, updated_row, timestamp))
                        logger.info(f"Batch {completed}/{len(batches)}: Log {log_number}: Fixed to {timestamp} (pending re-verification)")
                    else:
                        manual_check_faults.append(row.to_dict())
                        logger.info(f"Batch {completed}/{len(batches)}: Log {log_number}: Could not fix")
                    
            except KeyboardInterrupt:
                logger.info("Batch timestamp fixing interrupted")
                break
            except Exception as e:
                logger.error(f"Batch {completed}/{len(batches)} failed: {e}")
                # On error, mark all faults in the batch for manual review
    
    # Batched re-verification step
    if fixed_candidates:
        logger.info(f"Re-verifying {len(fixed_candidates)} fixed faults in batches of up to {batch_size}...")
        fixed_df, manual_check_from_verify = _batched_reverify_fixed(fixed_candidates, batch_size, max_workers, agent)
        manual_check_faults.extend(manual_check_from_verify)
    else:
        fixed_df = pd.DataFrame()
    
    # Save results
    if fixed_df is not None and len(fixed_df) > 0:
        fixed_df.to_csv(FIXED_CSV, index=False)
        logger.info(f"Saved {len(fixed_df)} fixed faults to {FIXED_CSV}")
    else:
        fixed_df = pd.DataFrame(columns=inaccurate_df.columns) if inaccurate_df is not None else pd.DataFrame()
    
    if manual_check_faults:
        manual_df = pd.DataFrame(manual_check_faults)
        # Ensure only expected columns are written (remove fix_confidence and verification_status)
        expected_cols = [c for c in inaccurate_df.columns if c not in ('fix_confidence', 'verification_status')]
        manual_df = manual_df[[c for c in expected_cols if c in manual_df.columns]]
        # Append to existing manual_check.csv
        if MANUAL_CHECK_CSV.exists() and MANUAL_CHECK_CSV.stat().st_size > 0:
            manual_df.to_csv(MANUAL_CHECK_CSV, mode='a', index=False, header=False)
            logger.info(f"Appended {len(manual_check_faults)} faults needing manual review to {MANUAL_CHECK_CSV}")
        else:
            manual_df.to_csv(MANUAL_CHECK_CSV, mode='w', index=False, header=True)
            logger.info(f"Created {MANUAL_CHECK_CSV} with {len(manual_check_faults)} faults needing manual review")
    else:
        manual_df = pd.DataFrame(columns=inaccurate_df.columns) if inaccurate_df is not None else pd.DataFrame()
    
    logger.info(f"Batched fixing complete: {len(fixed_df) if len(fixed_df) > 0 else 0} fixed, {len(manual_check_faults)} manual check, total: {len(inaccurate_df)}")
    
    return fixed_df, manual_df


def _batched_reverify_fixed(fixed_candidates: List[Tuple[int, str, dict, str]], batch_size: int, max_workers: int, agent: str = None) -> Tuple[pd.DataFrame, List[dict]]:
    """
    Re-verify fixed timestamps in batches for improved throughput.
    
    Args:
        fixed_candidates: List of (orig_idx, log_number, updated_row, timestamp) tuples
        batch_size: Number of faults per batch for re-verification
        max_workers: Number of parallel batch workers
        agent: openclaw agent name
        
    Returns:
        Tuple of (fixed_df, manual_check_list)
    """
    if agent is None:
        agent = AGENT_NAME
    
    # Load shift summaries once
    logger.info("Loading shift summaries for re-verification...")
    shift_summaries = {}
    shift_df = load_shift_summaries()
    if shift_df is not None:
        for idx, row in shift_df.iterrows():
            log_num = str(row.get('LogNumber', ''))
            content = row.get('NormalizedContent') or row.get('Content', '')
            if content:
                shift_summaries[log_num] = str(content)
        logger.info(f"Loaded {len(shift_summaries)} shift summaries")
    
    # Group candidates by log number (same log = same shift summary)
    candidates_by_log = {}
    for orig_idx, log_number, updated_row, timestamp in fixed_candidates:
        if log_number not in candidates_by_log:
            candidates_by_log[log_number] = []
        candidates_by_log[log_number].append((orig_idx, log_number, updated_row, timestamp))
    
    # Create batches for re-verification
    batches = []
    for log_number, candidate_list in candidates_by_log.items():
        shift_summary = shift_summaries.get(log_number, "")
        
        # Split into chunks of batch_size
        for i in range(0, len(candidate_list), batch_size):
            chunk = candidate_list[i:i + batch_size]
            batch_data = []
            for local_idx, (orig_idx, log_num, updated_row, timestamp) in enumerate(chunk):
                desc = updated_row.get('description', '')
                batch_data.append((local_idx, orig_idx, timestamp, desc, log_number))
            batches.append((batch_data, shift_summary))
    
    logger.info(f"Re-verifying in {len(batches)} batches of up to {batch_size}...")
    
    # Process re-verification batches in parallel
    fixed_rows = []
    manual_check_rows = []
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(verify_timestamps_batch, batch_data, shift_summary, agent): idx
            for idx, (batch_data, shift_summary) in enumerate(batches)
        }
        
        for future in as_completed(futures):
            completed += 1
            try:
                results = future.result()
                
                for orig_idx, is_accurate in results:
                    # Find the corresponding candidate
                    for cand_orig_idx, log_number, updated_row, timestamp in fixed_candidates:
                        if cand_orig_idx == orig_idx:
                            if is_accurate:
                                updated_row['fix_confidence'] = 'high'
                                fixed_rows.append(updated_row)
                                logger.info(f"Re-verify {completed}/{len(batches)}: Log {log_number}: Verified as accurate")
                            else:
                                updated_row['fix_confidence'] = 'low'
                                manual_check_rows.append(updated_row)
                                logger.info(f"Re-verify {completed}/{len(batches)}: Log {log_number}: Verification failed (low confidence)")
                            break
                    
            except Exception as e:
                logger.error(f"Re-verify batch {completed}/{len(batches)} failed: {e}")
                # On error, mark all in batch for manual review
    
    fixed_df = pd.DataFrame(fixed_rows) if fixed_rows else pd.DataFrame()
    return fixed_df, manual_check_rows


def _process_logbook_batch(batch_data: List[Tuple[int, int, str, str]], log_number: str, agent: str = None) -> List[Tuple[int, str, str]]:
    """
    Process a batch of faults from the same logbook entry.
    
    Args:
        batch_data: List of (local_idx, original_row_idx, description, log_number) tuples
        log_number: Log number to fetch logbook entry for
        agent: openclaw agent name
        
    Returns:
        List of (original_row_idx, corrected_timestamp, status) tuples
    """
    # Fetch the logbook entry
    logbook_content = get_logbook_entry_by_log_number(log_number)
    
    if not logbook_content:
        logger.warning(f"Could not fetch logbook {log_number}")
        return [(orig_idx, '', 'none') for _, orig_idx, _, _ in batch_data]
    
    # Process the batch
    return fix_timestamps_batch(batch_data, logbook_content, agent)


def load_shift_summaries() -> Optional[pd.DataFrame]:
    """
    Load shift summaries from CSV.
    
    Returns:
        DataFrame with shift summaries or None
    """
    try:
        from config import SHIFT_SUMMARY_CSV
        df = pd.read_csv(SHIFT_SUMMARY_CSV)
        logger.debug(f"Loaded shift summaries: {len(df)} rows")
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
    from config import SHIFT_SUMMARY_CSV
    try:
        shift_df = pd.read_csv(SHIFT_SUMMARY_CSV)
        
        logger.debug(f"Looking for log_number: {log_number} (type: {type(log_number).__name__})")
        logger.debug(f"Available LogNumbers: {shift_df['LogNumber'].head().tolist()}")
        logger.debug(f"LogNumber dtype: {shift_df['LogNumber'].dtype}")
        
        # Handle both string and integer log numbers by converting both to string
        log_number_str = str(log_number).strip()
        
        row = shift_df[shift_df['LogNumber'].astype(str).str.strip() == log_number_str]
        
        if len(row) == 0:
            logger.warning(f"No shift summary found for log {log_number_str}")
            return None
        
        content = row.iloc[0].get('NormalizedContent') or row.iloc[0].get('Content', '')
        return str(content) if content else None
    except Exception as e:
        logger.error(f"Failed to get shift summary: {e}")
        return None


def main_function4(agent: str = None, max_workers: int = 4, batch_size: int = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Main entry point for timestamp fixing.
    
    Args:
        agent: openclaw agent name
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many faults per batch (None = no batching)
        
    Returns:
        Tuple of (fixed_df, manual_check_df)
    """
    logger.info("Starting timestamp fixing")
    return fix_timestamps(agent, max_workers, batch_size)
