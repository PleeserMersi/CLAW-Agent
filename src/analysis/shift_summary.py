"""
Optimized fault extraction from shift summaries.
Uses batch processing, caching, and efficient timestamp handling.
"""
import csv
import time
import re
import json as stdlib_json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from pydantic import BaseModel

from config import (
    SHIFT_SUMMARY_CSV, PROCESSED_SUMMARIES_CSV,
    BASE_DIR, AGENT_NAME
)
from utils.llm_utils import (
    call_llm, PROMPT_TEMPLATES
)
from utils.text_utils import normalize_timestamp, parse_timestamp_to_datetime
from utils.logging_utils import logger
from utils.shutdown import is_shutdown_requested
from analysis.link_logic import create_text_fragment_link


# Pydantic models for structured output
class Fault(BaseModel):
    timestamp: str
    description: str
    tag: Optional[str] = None
    run_number: Optional[str] = None


def _extract_fallback_timestamp(timestamp_str: str) -> Optional[str]:
    """
    Attempt to extract/normalize a timestamp from various formats.
    
    Handles common LLM output formats that normalize_timestamp might miss:
    - "0:30 AM" -> "00:30"
    - "1412" -> "14:12" (military time without colon)
    - "14:44" -> "14:44"
    - "1503" -> "15:03"
    - "2:30pm" -> "14:30"
    - "~45min into run" -> try to extract time context
    - "17:00-18:20" -> extract first time "17:00"
    - "around 9PM" -> "21:00"
    - "before 00:37" -> "00:37" (extract the time)
    
    Args:
        timestamp_str: Raw timestamp string from LLM
        
    Returns:
        Normalized HH:MM timestamp, or None if unparseable
    """
    if not timestamp_str:
        return None
    
    ts = timestamp_str.strip()
    
    # Skip clearly unparseable patterns
    unparseable_patterns = [
        r'^n/a$', r'^unspecified$', r'^beginning$', r'^shift$', 
        r'^start$', r'^end$', r'^before start$', r'^last \d+ hours',
        r'^during run', r'^before \d', r'^around\s+\d',
    ]
    for pattern in unparseable_patterns:
        if re.match(pattern, ts, re.IGNORECASE):
            # Check if there's an extractable time within the unparseable text
            time_match = re.search(r'(\d{1,2}):(\d{2})', ts)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return f"{hour:02d}:{minute:02d}"
            return None
    
    # Try standard normalization first (in case it works now)
    from utils.text_utils import normalize_timestamp
    result = normalize_timestamp(ts)
    if result:
        return result
    
    # Pattern 1: Time range (e.g., "17:00-18:20", "19:45-23:45") - extract first time
    range_match = re.match(r'^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$', ts)
    if range_match:
        hour = int(range_match.group(1))
        minute = int(range_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    
    # Pattern 2: Military time without colon (e.g., "1412", "1503", "0930")
    military_match = re.match(r'^(\d{2})(\d{2})$', ts)
    if military_match:
        hour = int(military_match.group(1))
        minute = int(military_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    
    # Pattern 3: AM/PM format with space (e.g., "0:30 AM", "2:30 PM")
    am_pm_match = re.match(r'^(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)$', ts, re.IGNORECASE)
    if am_pm_match:
        hour = int(am_pm_match.group(1))
        minute = int(am_pm_match.group(2))
        period = am_pm_match.group(3).upper()
        
        if 0 <= hour <= 12 and 0 <= minute <= 59:
            if period == 'PM' and hour != 12:
                hour += 12
            elif period == 'AM' and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"
    
    # Pattern 4: AM/PM without space (e.g., "0:30AM", "2:30pm")
    am_pm_nospace = re.match(r'^(\d{1,2}):(\d{2})(AM|PM|am|pm)$', ts, re.IGNORECASE)
    if am_pm_nospace:
        hour = int(am_pm_nospace.group(1))
        minute = int(am_pm_nospace.group(2))
        period = am_pm_nospace.group(3).upper()
        
        if 0 <= hour <= 12 and 0 <= minute <= 59:
            if period == 'PM' and hour != 12:
                hour += 12
            elif period == 'AM' and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"
    
    # Pattern 5: "around Xpm" or "around X am" (e.g., "around 9PM")
    around_match = re.match(r'^around\s+(\d{1,2})(AM|PM|am|pm)$', ts, re.IGNORECASE)
    if around_match:
        hour = int(around_match.group(1))
        period = around_match.group(2).upper()
        
        if 0 <= hour <= 12:
            if period == 'PM' and hour != 12:
                hour += 12
            elif period == 'AM' and hour == 12:
                hour = 0
            return f"{hour:02d}:00"
    
    # Pattern 6: "Xpm" or "X am" without colon (e.g., "9pm", "2 am")
    simple_am_pm = re.match(r'^(\d{1,2})(AM|PM|am|pm)$', ts, re.IGNORECASE)
    if simple_am_pm:
        hour = int(simple_am_pm.group(1))
        period = simple_am_pm.group(2).upper()
        
        if 0 <= hour <= 12:
            if period == 'PM' and hour != 12:
                hour += 12
            elif period == 'AM' and hour == 12:
                hour = 0
            return f"{hour:02d}:00"
    
    # Pattern 7: "~Xhr into run" or "~Xmin into run" - cannot determine exact time, skip
    # These require context about run start time which we don't have
    relative_match = re.match(r'^~?(\d+)(hr|min|hour|minute)s?\s+into\s+run', ts, re.IGNORECASE)
    if relative_match:
        # Cannot determine absolute time without run start time
        return None
    
    # Pattern 8: 3-digit military time (e.g., "930" for 09:30)
    short_military = re.match(r'^(\d{3,4})$', ts)
    if short_military:
        val = short_military.group(1)
        if len(val) == 3:
            hour = int(val[0])
            minute = int(val[1:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"
    
    # Pattern 9: Just hours (e.g., "14" for 14:00)
    just_hours = re.match(r'^(\d{1,2})$', ts)
    if just_hours:
        hour = int(just_hours.group(1))
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
    
    # Pattern 10: Extract any HH:MM pattern from messy text
    time_extract = re.search(r'(\d{1,2}):(\d{2})', ts)
    if time_extract:
        hour = int(time_extract.group(1))
        minute = int(time_extract.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    
    return None


class FaultReport(BaseModel):
    faults: List[Fault] = []


def extract_faults_from_summary(shift_summary: str, agent: str = None) -> FaultReport:
    """
    Extract faults from a single shift summary using LLM.
    
    Args:
        shift_summary: Text content of shift summary
        agent: openclaw agent name (defaults to AGENT_NAME)
        
    Returns:
        FaultReport with extracted faults
    """
    # Use string replacement instead of .format() to avoid issues with curly braces
    prompt = PROMPT_TEMPLATES["fault_extraction"].replace("{shift_summary}", shift_summary)
    
    response = call_llm(
        prompt=prompt,
        agent=agent
    )
    
    if not response:
        logger.warning("No response from LLM")
        return FaultReport(faults=[])
    
    logger.debug(f"LLM response: {response[:500]}")
    
    try:
        # Clean up response - extract JSON array if there's extra text
        json_match = re.search(r'\[.*\]', response, re.DOTALL | re.IGNORECASE)
        if json_match:
            json_str = json_match.group(0)
            try:
                return FaultReport.model_validate_json(json_str)
            except Exception:
                try:
                    faults_list = stdlib_json.loads(json_str)
                    if isinstance(faults_list, list):
                        for fault in faults_list:
                            if isinstance(fault, dict) and "run_number" in fault:
                                if fault["run_number"] is not None:
                                    fault["run_number"] = str(fault["run_number"])
                        return FaultReport(faults=faults_list)
                    return FaultReport(faults=[])
                except Exception as parse_error:
                    logger.warning(f"JSON parse failed: {parse_error}")
                    logger.warning(f"Extracted JSON: {json_str[:200]}")
                    fault_matches = re.findall(r'\{[^{}]*\}', json_str)
                    if fault_matches:
                        faults = []
                        for fm in fault_matches:
                            try:
                                fault = Fault.model_validate_json(fm)
                                faults.append(fault)
                            except:
                                pass
                        return FaultReport(faults=faults)
                    return FaultReport(faults=[])
        else:
            try:
                return FaultReport.model_validate_json(response)
            except Exception:
                return FaultReport(faults=[])
    except Exception as e:
        logger.error(f"Failed to parse fault report: {e}")
        logger.warning(f"Full response: {response}")
        return FaultReport(faults=[])


def extract_faults_batch(shift_batch: List[pd.Series], agent: str = None) -> List[Tuple[int, List[dict]]]:
    """
    Extract faults from multiple shift summaries in a single batched LLM call.
    
    Args:
        shift_batch: List of DataFrame rows (shift summaries) to process
        agent: openclaw agent name (defaults to AGENT_NAME)
        
    Returns:
        List of (source_index, faults_list) tuples
    """
    # Build the summaries block
    summaries_block = ""
    for idx, row in enumerate(shift_batch):
        content = row.get('NormalizedContent') or row.get('Content', '')
        if pd.notna(content) and content:
            summaries_block += f"--- SUMMARY {idx} ---\n{content}\n\n"
    
    if not summaries_block.strip():
        logger.warning("No valid content in batch")
        return [(i, []) for i in range(len(shift_batch))]
    
    # Use string replacement for the prompt
    prompt = PROMPT_TEMPLATES["fault_extraction_batch"].replace(
        "{summaries_block}", summaries_block
    )
    
    response = call_llm(prompt=prompt, agent=agent)
    
    if not response:
        logger.warning("No response from LLM for batch")
        return [(i, []) for i in range(len(shift_batch))]
    
    logger.debug(f"Batch LLM response (first 500 chars): {response[:500]}")
    
    # Parse the batched response
    results = [(i, []) for i in range(len(shift_batch))]
    
    try:
        # Try to extract JSON array
        json_match = re.search(r'\[.*\]', response, re.DOTALL | re.IGNORECASE)
        if not json_match:
            logger.warning("No JSON array found in batch response: (" + response + ")")
            return results
        
        json_str = json_match.group(0)
        batch_data = stdlib_json.loads(json_str)
        
        if not isinstance(batch_data, list):
            logger.warning(f"Expected list, got {type(batch_data)}")
            return results
        
        # Process each batch item
        for item in batch_data:
            if not isinstance(item, dict):
                continue
            
            source_idx = item.get("source_index")
            faults_list = item.get("faults", [])
            
            if source_idx is None or source_idx >= len(shift_batch):
                logger.warning(f"Invalid source_index: {source_idx}")
                continue
            
            # Process faults and add metadata
            processed_faults = []
            for fault in faults_list:
                if not isinstance(fault, dict):
                    continue
                
                # Ensure run_number is string
                if "run_number" in fault and fault["run_number"] is not None:
                    fault["run_number"] = str(fault["run_number"])
                
                processed_faults.append(fault)
            
            results[source_idx] = (source_idx, processed_faults)
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to parse batch response: {e}")
        logger.warning(f"Full response: {response}")
        return results


def _process_single_row(row: pd.Series, agent: str = None) -> Tuple[str, List[dict], bool]:
    """
    Worker function to process a single shift summary row.
    Thread-safe for use in ThreadPoolExecutor.
    
    Args:
        row: DataFrame row with shift summary data
        agent: openclaw agent name
        
    Returns:
        Tuple of (log_number, list of fault records, success flag)
    """
    log_number = row.get('LogNumber', 'Unknown')
    
    # Extract date
    shift_date = None
    if pd.notna(row.get('DateTime')):
        try:
            if isinstance(row['DateTime'], (datetime, pd.Timestamp)):
                shift_date = row['DateTime'].date()
            else:
                shift_date = pd.to_datetime(row['DateTime']).date()
        except Exception as e:
            logger.warning(f"Invalid DateTime for LogNumber {log_number}: {e}")
            return str(log_number), [], False
    
    # Extract content
    content = row.get('NormalizedContent') or row.get('Content', '')
    if pd.isna(content) or not content:
        return str(log_number), [], True  # No content, not an error
    
    try:
        fault_report = extract_faults_from_summary(str(content), agent=agent)
        
        faults = []
        for fault in fault_report.faults:
            normalized_time = normalize_timestamp(fault.timestamp)
            
            # Handle 24:00 case - normalize_timestamp returns None for 24:00
            # We need to check the original timestamp for 24:00
            original_time = fault.timestamp.strip() if fault.timestamp else ""
            is_2400 = False
            if not normalized_time and original_time:
                # Check if it's 24:00 (with or without cleaning)
                clean_time = re.sub(r'[^0-9:]', '', original_time)
                if clean_time == "24:00":
                    is_2400 = True
                    # Pass "24:00" to parse_timestamp_to_datetime which will handle the rollover
                    normalized_time = "24:00"
            
            if not normalized_time:
                # Fallback: Try to extract timestamp from the raw response
                # Common patterns: "0:30 AM", "1412", "14:44", "1503", etc.
                original_time = fault.timestamp.strip() if fault.timestamp else ""
                fallback_time = _extract_fallback_timestamp(original_time)
                
                if fallback_time:
                    normalized_time = fallback_time
                else:
                    logger.warning(f"Invalid timestamp for Log {log_number}: {fault.timestamp}")
                    continue
            
            fault_datetime = None
            if shift_date:
                fault_datetime = parse_timestamp_to_datetime(
                    shift_date.strftime("%Y-%m-%d"),
                    normalized_time
                )
            
            fault_record = {
                'FullTimestamp': fault_datetime,
                'timestamp': normalized_time,
                'description': fault.description if fault.description else 'No description',
                'tag': fault.tag if fault.tag else 'Other',
                'run_number': fault.run_number,
                'ShiftLogNumber': log_number,
                'ShiftLogbookURL': row.get('LogbookURL'),
                'ShiftTitle': row.get('Title'),
                'ShiftDateTime': row.get('DateTime'),
                'ShiftHall': row.get('Hall', 'Unknown'),
                'FragmentLink': ''
            }
            
            if fault_datetime and fault_record['ShiftLogbookURL']:
                fault_record['FragmentLink'] = create_text_fragment_link(
                    fault_record['ShiftLogbookURL'],
                    fault_datetime.strftime("%H:%M"),
                    "."
                )
            
            faults.append(fault_record)
        
        return str(log_number), faults, True
        
    except Exception as e:
        logger.error(f"Error processing shift {log_number}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return str(log_number), [], False


def _process_faults_batched(
    shift_data_df: pd.DataFrame,
    batch_size: int,
    max_workers: int,
    agent: str = None
) -> pd.DataFrame:
    """
    Process shift summaries in batches for improved throughput.
    
    Args:
        shift_data_df: DataFrame with shift summaries
        batch_size: Number of summaries per batch
        max_workers: Number of parallel batch workers
        agent: openclaw agent name
        
    Returns:
        DataFrame with all extracted faults
    """
    all_faults = []
    
    # Filter out rows with no content first
    valid_rows = shift_data_df[
        shift_data_df.apply(
            lambda r: pd.notna(r.get('NormalizedContent') or r.get('Content', '')) 
                      and (r.get('NormalizedContent') or r.get('Content', '')) != '', 
            axis=1
        )
    ].reset_index(drop=True)
    
    valid_count = len(valid_rows)
    if valid_count == 0:
        logger.warning("No valid shift summaries to process")
        return pd.DataFrame(columns=[
            'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
            'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 'ShiftHall', 'FragmentLink'
        ])
    
    # Create date mapping for batch processing
    date_map = {}
    for idx, row in valid_rows.iterrows():
        shift_date = None
        if pd.notna(row.get('DateTime')):
            try:
                if isinstance(row['DateTime'], (datetime, pd.Timestamp)):
                    shift_date = row['DateTime'].date()
                else:
                    shift_date = pd.to_datetime(row['DateTime']).date()
            except Exception as e:
                logger.warning(f"Invalid DateTime for LogNumber {row.get('LogNumber')}: {e}")
        date_map[idx] = shift_date
    
    # Split into batches
    batches = []
    for i in range(0, valid_count, batch_size):
        batch_indices = list(range(i, min(i + batch_size, valid_count)))
        batches.append((batch_indices, [valid_rows.iloc[idx] for idx in batch_indices]))
    
    logger.info(f"Processing {valid_count} summaries in {len(batches)} batches of up to {batch_size} each")
    
    # Process batches in parallel
    completed = 0
    success_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_batch, batch_indices, batch_rows, date_map, agent): idx
            for idx, (batch_indices, batch_rows) in enumerate(batches)
        }
        
        for future in as_completed(futures):
            completed += 1
            # Check for shutdown
            if is_shutdown_requested():
                logger.info("Batch fault extraction interrupted by shutdown request")
                break
            try:
                batch_results = future.result()
                success_count += 1
                
                for log_number, faults in batch_results:
                    all_faults.extend(faults)
                    if faults:
                        logger.info(
                            f"Batch {completed}/{len(batches)}: Log {log_number} - "
                            f"{len(faults)} faults extracted"
                        )
                    
            except KeyboardInterrupt:
                logger.info("Batch fault extraction interrupted")
                break
            except Exception as e:
                failed_count += 1
                logger.error(f"Batch {completed}/{len(batches)} failed: {e}")
    
    # Log summary
    logger.info(
        f"Batched fault extraction completed: {success_count} successful, "
        f"{failed_count} failed, {len(all_faults)} total faults extracted"
    )
    
    # Create DataFrame
    if all_faults:
        faults_df = pd.DataFrame(all_faults)
        faults_df['FullTimestamp'] = pd.to_datetime(faults_df['FullTimestamp'], errors='coerce')
        
        expected_cols = [
            'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
            'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 'ShiftHall', 'FragmentLink'
        ]
        for col in expected_cols:
            if col not in faults_df.columns:
                faults_df[col] = None
        
        faults_df = faults_df[expected_cols]
        return faults_df
    else:
        return pd.DataFrame(columns=[
            'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number', 'ShiftHall',
            'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 'FragmentLink'
        ])


def _process_batch(batch_indices: List[int], batch_rows: List[pd.Series], date_map: Dict[int, datetime.date], agent: str = None) -> List[Tuple[str, List[dict]]]:
    """
    Process a single batch of shift summaries.
    
    Args:
        batch_indices: Original indices of rows in the batch
        batch_rows: List of DataFrame rows in the batch
        date_map: Mapping of original index to shift date
        agent: openclaw agent name
        
    Returns:
        List of (log_number, faults_list) tuples
    """
    # Get batched extraction results
    batch_results = extract_faults_batch(batch_rows, agent=agent)
    
    results = []
    for local_idx, (source_idx, faults_list) in enumerate(batch_results):
        if local_idx >= len(batch_rows):
            continue
            
        row = batch_rows[local_idx]
        log_number = str(row.get('LogNumber', 'Unknown'))
        shift_date = date_map.get(batch_indices[local_idx])
        
        faults = []
        for fault in faults_list:
            timestamp_str = fault.get('timestamp', '')
            if not timestamp_str:
                continue
                
            normalized_time = normalize_timestamp(timestamp_str)
            
            # Handle 24:00 case
            if not normalized_time and timestamp_str:
                clean_time = re.sub(r'[^0-9:]', '', timestamp_str)
                if clean_time == "24:00":
                    normalized_time = "24:00"
            
            if not normalized_time:
                # Fallback: Try to extract timestamp from the raw response
                fallback_time = _extract_fallback_timestamp(timestamp_str)
                
                if fallback_time:
                    normalized_time = fallback_time
                else:
                    logger.warning(f"Invalid timestamp for Log {log_number}: {timestamp_str}")
                    continue
            
            fault_datetime = None
            if shift_date:
                fault_datetime = parse_timestamp_to_datetime(
                    shift_date.strftime("%Y-%m-%d"),
                    normalized_time
                )
            
            fault_record = {
                'FullTimestamp': fault_datetime,
                'timestamp': normalized_time,
                'description': fault.get('description', 'No description'),
                'tag': 'Other',  # Tags added later
                'run_number': fault.get('run_number'),
                'ShiftLogNumber': log_number,
                'ShiftLogbookURL': row.get('LogbookURL'),
                'ShiftTitle': row.get('Title'),
                'ShiftDateTime': row.get('DateTime'),
                'ShiftHall': row.get('Hall', 'Unknown'),
                'FragmentLink': ''
            }
            
            if fault_datetime and fault_record['ShiftLogbookURL']:
                fault_record['FragmentLink'] = create_text_fragment_link(
                    fault_record['ShiftLogbookURL'],
                    fault_datetime.strftime("%H:%M"),
                    "."
                )
            
            faults.append(fault_record)
        
        results.append((log_number, faults))
    
    return results


def process_faults_with_shift_data(
    shift_data_df: pd.DataFrame,
    max_workers: int = 4,
    agent: str = None,
    batch_size: int = None
) -> pd.DataFrame:
    """
    Process all shift summaries to extract faults using parallel processing.
    Supports both single-item processing and batched processing.
    
    Args:
        shift_data_df: DataFrame with shift summaries
        max_workers: Number of parallel workers (default: 4, optimal based on benchmark)
        agent: openclaw agent name
        batch_size: If set, process this many summaries per batch (None = no batching)
        
    Returns:
        DataFrame with all extracted faults
    """
    all_faults = []
    total_rows = len(shift_data_df)
    
    # Ensure output directories exist
    PROCESSED_SUMMARIES_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    if batch_size and batch_size > 1:
        logger.info(f"Starting fault extraction with batching (size={batch_size}, workers={max_workers})...")
        return _process_faults_batched(shift_data_df, batch_size, max_workers, agent)
    
    logger.info(f"Starting fault extraction with {max_workers} parallel workers...")
    
    # Filter out rows with no content first
    valid_rows = shift_data_df[
        shift_data_df.apply(
            lambda r: pd.notna(r.get('NormalizedContent') or r.get('Content', '')) 
                      and (r.get('NormalizedContent') or r.get('Content', '')) != '', 
            axis=1
        )
    ].reset_index(drop=True)
    
    valid_count = len(valid_rows)
    if valid_count == 0:
        logger.warning("No valid shift summaries to process")
        return pd.DataFrame(columns=[
            'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
            'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 'ShiftHall', 'FragmentLink'
        ])
    
    # Process in parallel using ThreadPoolExecutor
    completed = 0
    success_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(_process_single_row, row, agent): idx
            for idx, row in valid_rows.iterrows()
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            completed += 1
            try:
                log_number, faults, success = future.result()
                
                if success:
                    success_count += 1
                    all_faults.extend(faults)
                    logger.info(
                        f"[{completed}/{valid_count}] Log {log_number}: "
                        f"{len(faults)} faults extracted"
                    )
                else:
                    failed_count += 1
                    logger.warning(f"[{completed}/{valid_count}] Log {log_number}: Processing failed")
                    
            except Exception as e:
                failed_count += 1
                idx = futures[future]
                logger.error(f"[{completed}/{valid_count}] Row {idx} failed with exception: {e}")
    
    # Log summary
    logger.info(
        f"Fault extraction completed: {success_count} successful, "
        f"{failed_count} failed, {len(all_faults)} total faults extracted"
    )
    
    # Create DataFrame
    if all_faults:
        faults_df = pd.DataFrame(all_faults)
        faults_df['FullTimestamp'] = pd.to_datetime(faults_df['FullTimestamp'], errors='coerce')
        
        expected_cols = [
            'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
            'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 'ShiftHall', 'FragmentLink'
        ]
        for col in expected_cols:
            if col not in faults_df.columns:
                faults_df[col] = None
        
        faults_df = faults_df[expected_cols]
        return faults_df
    else:
        return pd.DataFrame(columns=[
            'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number', 'ShiftHall',
            'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 'FragmentLink'
        ])


def main_function2(agent: str = None, max_workers: int = 4, batch_size: int = None) -> tuple:
    """
    Main entry point for fault extraction pipeline.
    
    Args:
        agent: openclaw agent name (defaults to AGENT_NAME)
        max_workers: Number of parallel workers (default: 4)
        batch_size: If set, process this many summaries per batch (None = no batching)
        
    Returns:
        Tuple of (DataFrame with faults, start_time)
    """
    start_time = time.time()
    
    logger.info("Starting fault extraction")
    
    try:
        shift_df = pd.read_csv(SHIFT_SUMMARY_CSV)
        logger.info(f"Loaded {len(shift_df)} shift summaries")
    except Exception as e:
        logger.error(f"Failed to load shift summaries: {e}")
        return pd.DataFrame(), start_time
    
    faults_df = process_faults_with_shift_data(shift_df, max_workers=max_workers, agent=agent, batch_size=batch_size)
    
    # Note: Do NOT save here - tags haven't been added yet
    # The caller (pipeline.py) will save after tagging
    
    return faults_df, start_time
