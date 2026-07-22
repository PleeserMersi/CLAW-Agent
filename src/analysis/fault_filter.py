"""
Fault filtering module.
Validates extracted faults with LLM to remove non-fault entries.
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from config import (
    PROCESSED_SUMMARIES_CSV, NOT_FAULTS_CSV, BASE_DIR, AGENT_NAME
)
from utils.llm_utils import call_llm, PROMPT_TEMPLATES
from utils.logging_utils import logger
from utils.shutdown import is_shutdown_requested

stdlib_json = json


def _validate_single_fault(row: pd.Series, agent: str = None) -> Tuple[str, bool]:
    """
    Worker function to validate a single fault.
    Thread-safe for use in ThreadPoolExecutor.
    
    Args:
        row: DataFrame row with fault data
        agent: openclaw agent name
        
    Returns:
        Tuple of (log_number, is_valid)
    """
    log_number = str(row.get('ShiftLogNumber', 'Unknown'))
    description = row.get('description', '')
    
    if not description:
        return log_number, True  # Empty description - keep it
    
    if agent is None:
        agent = AGENT_NAME
    
    prompt = PROMPT_TEMPLATES["fault_validation"].format(description=description)
    
    reply = call_llm(prompt, agent=agent)
    
    if reply:
        result = reply.strip().lower()
        return log_number, result == "yes"
    
    # Default to True if we can't get a response (conservative approach)
    logger.warning(f"No LLM response for fault validation: {description}")
    return log_number, True


def is_valid_fault(description: str, agent: str = None) -> bool:
    """
    Validate if a description represents a valid fault using LLM.
    
    Args:
        description: Fault description to validate
        agent: openclaw agent name (defaults to AGENT_NAME)
        
    Returns:
        True if it's a valid fault, False otherwise
    """
    if agent is None:
        agent = AGENT_NAME
    
    prompt = PROMPT_TEMPLATES["fault_validation"].format(description=description)
    
    reply = call_llm(prompt, agent=agent)
    
    if reply:
        result = reply.strip().lower()
        return result == "yes"
    
    # Default to True if we can't get a response (conservative approach)
    logger.warning(f"No LLM response for fault validation: {description}")
    return True


def validate_faults_batch(batch_data: List[Tuple[int, int, str]], agent: str = None) -> List[Tuple[int, bool]]:
    """
    Validate multiple faults in a single batched LLM call.
    
    Args:
        batch_data: List of (local_idx, original_row_idx, description) tuples
        agent: openclaw agent name
        
    Returns:
        List of (original_row_idx, is_valid) tuples
    """
    if not batch_data:
        return []
    
    # Build the faults block with local indices
    faults_block = ""
    for local_idx, orig_idx, description in batch_data:
        faults_block += f"--- FAULT {local_idx} (original row {orig_idx}) ---\n{description}\n\n"
    
    if not faults_block.strip():
        return [(orig_idx, True) for _, orig_idx, _ in batch_data]
    
    prompt = PROMPT_TEMPLATES["fault_validation_batch"].format(faults_block=faults_block)
    
    response = call_llm(prompt=prompt, agent=agent)
    
    if not response:
        logger.warning("No response from LLM for batch validation")
        return [(orig_idx, True) for _, orig_idx, _ in batch_data]
    
    logger.debug(f"Batch validation response (first 500 chars): {response[:500]}")
    
    # Parse the batched response
    results = {}
    
    try:
        # Try to extract JSON array
        json_match = re.search(r'\[.*\]', response, re.DOTALL | re.IGNORECASE)
        if not json_match:
            logger.warning("No JSON array found in batch validation response")
            return [(orig_idx, True) for _, orig_idx, _ in batch_data]
        
        json_str = json_match.group(0)
        batch_data_parsed = stdlib_json.loads(json_str)
        
        if not isinstance(batch_data_parsed, list):
            logger.warning(f"Expected list, got {type(batch_data_parsed)}")
            return [(orig_idx, True) for _, orig_idx, _ in batch_data]
        
        # Create a map of local_idx to original_row_idx
        local_to_orig = {local_idx: orig_idx for local_idx, orig_idx, _ in batch_data}
        
        # Process each result
        for item in batch_data_parsed:
            if not isinstance(item, dict):
                continue
            
            local_idx = item.get("index")
            valid_str = item.get("valid", "Yes")
            
            if local_idx is None:
                continue
            
            is_valid = valid_str.strip().lower() == "yes"
            
            # Map local index to original row index
            if local_idx in local_to_orig:
                orig_idx = local_to_orig[local_idx]
                results[orig_idx] = (orig_idx, is_valid)
            else:
                logger.warning(f"Invalid local index in batch response: {local_idx}")
        
        # Return results in order of original batch_data
        return [results.get(orig_idx, (orig_idx, True)) for _, orig_idx, _ in batch_data]
        
    except Exception as e:
        logger.error(f"Failed to parse batch validation response: {e}")
        logger.warning(f"Full response: {response}")
        return [(orig_idx, True) for _, orig_idx, _ in batch_data]


def filter_faults(faults_df: pd.DataFrame = None, agent: str = None, max_workers: int = 4, batch_size: int = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Filter extracted faults, removing non-fault entries using parallel processing.
    Supports both single-item processing and batched processing.
    
    Args:
        faults_df: DataFrame of faults to filter (if None, loads from PROCESSED_SUMMARIES_CSV)
        agent: openclaw agent name
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many faults per batch (None = no batching)
        
    Returns:
        Tuple of (valid_faults_df, removed_faults_df)
    """
    # Load faults if not provided
    if faults_df is None:
        if not PROCESSED_SUMMARIES_CSV.exists():
            logger.error(f"Processed summaries not found: {PROCESSED_SUMMARIES_CSV}")
            return None, None
        
        try:
            faults_df = pd.read_csv(PROCESSED_SUMMARIES_CSV)
            logger.info(f"Loaded {len(faults_df)} faults for filtering from file")
        except Exception as e:
            logger.error(f"Failed to load faults: {e}")
            return None, None
    else:
        logger.info(f"Loaded {len(faults_df)} faults for filtering from memory")
    
    if len(faults_df) == 0:
        logger.info("No faults to filter")
        return faults_df, pd.DataFrame(columns=faults_df.columns)
    
    if agent is None:
        agent = AGENT_NAME
    
    # Ensure output directories exist
    NOT_FAULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    if batch_size and batch_size > 1:
        logger.info(f"Starting fault filtering with batching (size={batch_size}, workers={max_workers})...")
        return _filter_faults_batched(faults_df, batch_size, max_workers, agent)
    
    logger.info(f"Starting fault filtering with {max_workers} parallel workers...")
    
    valid_faults = []
    removed_faults = []
    
    total = len(faults_df)
    valid_count = 0
    removed_count = 0
    completed = 0
    
    # Process in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_validate_single_fault, row, agent): idx
            for idx, row in faults_df.iterrows()
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Fault filtering interrupted by shutdown request")
                break
            try:
                log_number, is_fault = future.result()
                idx = futures[future]
                row = faults_df.iloc[idx]
                
                if is_fault:
                    valid_faults.append(row.to_dict())
                    valid_count += 1
                    logger.info(f"[{completed}/{total}] Log {log_number}: VALID fault")
                else:
                    removed_faults.append(row.to_dict())
                    removed_count += 1
                    logger.info(f"[{completed}/{total}] Log {log_number}: REMOVED (not a fault)")
                    
            except KeyboardInterrupt:
                logger.info("Fault filtering interrupted")
                break
            except Exception as e:
                idx = futures[future]
                row = faults_df.iloc[idx]
                log_number = str(row.get('ShiftLogNumber', 'Unknown'))
                logger.error(f"[{completed}/{total}] Log {log_number}: Validation failed - {e}")
                # On error, keep the fault (conservative)
                valid_faults.append(row.to_dict())
                valid_count += 1
    
    # Save removed faults
    if removed_faults:
        removed_df = pd.DataFrame(removed_faults)
        removed_df.to_csv(NOT_FAULTS_CSV, index=False)
        logger.info(f"Saved {len(removed_faults)} removed faults to {NOT_FAULTS_CSV}")
    else:
        removed_df = pd.DataFrame(columns=faults_df.columns)
    
    # Return valid faults (not saved yet - caller will save)
    if valid_faults:
        valid_df = pd.DataFrame(valid_faults)
        # Ensure all columns are present
        expected_cols = faults_df.columns.tolist()
        for col in expected_cols:
            if col not in valid_df.columns:
                valid_df[col] = None
        valid_df = valid_df[expected_cols]
    else:
        valid_df = pd.DataFrame(columns=faults_df.columns)
    
    logger.info(f"Filtering complete: {valid_count} valid, {removed_count} removed, total: {total}")
    
    return valid_df, removed_df


def _filter_faults_batched(faults_df: pd.DataFrame, batch_size: int, max_workers: int, agent: str = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Filter faults in batches for improved throughput.
    
    Args:
        faults_df: DataFrame of faults to filter
        batch_size: Number of faults per batch
        max_workers: Number of parallel batch workers
        agent: openclaw agent name
        
    Returns:
        Tuple of (valid_faults_df, removed_faults_df)
    """
    if agent is None:
        agent = AGENT_NAME
    
    # Split into batches
    batches = []
    for i in range(0, len(faults_df), batch_size):
        batch = faults_df.iloc[i:i + batch_size]
        # Format: List of (local_idx, original_row_idx, description)
        batch_data = [(local_idx, idx, row.get('description', '')) 
                      for local_idx, (idx, row) in enumerate(batch.iterrows())]
        batches.append(batch_data)
    
    logger.info(f"Processing {len(faults_df)} faults in {len(batches)} batches of up to {batch_size}...")
    
    # Process batches in parallel
    valid_faults = []
    removed_faults = []
    valid_count = 0
    removed_count = 0
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(validate_faults_batch, batch_data, agent): idx
            for idx, batch_data in enumerate(batches)
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Batch fault filtering interrupted by shutdown request")
                break
            try:
                results = future.result()
                
                for orig_idx, is_valid in results:
                    row = faults_df.iloc[orig_idx]
                    log_number = str(row.get('ShiftLogNumber', 'Unknown'))
                    
                    if is_valid:
                        valid_faults.append(row.to_dict())
                        valid_count += 1
                        logger.info(f"Batch {completed}/{len(batches)}: Log {log_number}: VALID fault")
                    else:
                        removed_faults.append(row.to_dict())
                        removed_count += 1
                        logger.info(f"Batch {completed}/{len(batches)}: Log {log_number}: REMOVED (not a fault)")
                    
            except KeyboardInterrupt:
                logger.info("Batch fault filtering interrupted")
                break
            except Exception as e:
                logger.error(f"Batch {completed}/{len(batches)} failed: {e}")
                # On error, keep all faults in the batch (conservative)
                batch_start = (completed - 1) * batch_size
                batch_end = min(batch_start + batch_size, len(faults_df))
                for idx in range(batch_start, batch_end):
                    row = faults_df.iloc[idx]
                    valid_faults.append(row.to_dict())
                    valid_count += 1
    
    # Save removed faults
    if removed_faults:
        removed_df = pd.DataFrame(removed_faults)
        removed_df.to_csv(NOT_FAULTS_CSV, index=False)
        logger.info(f"Saved {len(removed_faults)} removed faults to {NOT_FAULTS_CSV}")
    else:
        removed_df = pd.DataFrame(columns=faults_df.columns)
    
    # Return valid faults
    if valid_faults:
        valid_df = pd.DataFrame(valid_faults)
        # Ensure all columns are present
        expected_cols = faults_df.columns.tolist()
        for col in expected_cols:
            if col not in valid_df.columns:
                valid_df[col] = None
        valid_df = valid_df[expected_cols]
    else:
        valid_df = pd.DataFrame(columns=faults_df.columns)
    
    logger.info(f"Batched filtering complete: {valid_count} valid, {removed_count} removed, total: {len(faults_df)}")
    
    return valid_df, removed_df


def main_function_filter(faults_df: pd.DataFrame = None, agent: str = None, max_workers: int = 4, batch_size: int = None) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Main entry point for fault filtering.
    
    Args:
        faults_df: DataFrame of faults to filter (if None, loads from file)
        agent: openclaw agent name
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many faults per batch (None = no batching)
        
    Returns:
        Tuple of (valid_faults_df, removed_faults_df)
    """
    logger.info("Starting fault filtering")
    return filter_faults(faults_df, agent, max_workers, batch_size)
