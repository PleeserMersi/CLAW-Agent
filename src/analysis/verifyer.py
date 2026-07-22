"""
Consolidation module.
Combines all verified and fixed faults into final output.
"""
import csv
from pathlib import Path
from typing import Optional

import pandas as pd

from config import (
    ALL_FAULTS_CSV, ACCURATE_CSV, FIXED_CSV, MANUAL_CHECK_CSV,
    BASE_DIR
)
from utils.logging_utils import logger


def consolidate_faults(agent: str = None) -> Optional[pd.DataFrame]:
    """
    Combine all verified and fixed faults into final output.
    
    Args:
        agent: openclaw agent name (unused - consolidation is a merge operation)
        
    Returns:
        DataFrame with all verified faults
    """
    all_faults = []
    
    # Load accurate faults
    if ACCURATE_CSV.exists():
        try:
            accurate_df = pd.read_csv(ACCURATE_CSV)
            accurate_df['verification_status'] = 'accurate'
            all_faults.append(accurate_df)
            logger.info(f"Loaded {len(accurate_df)} accurate faults")
        except Exception as e:
            logger.error(f"Failed to load accurate faults: {e}")
    
    # Load fixed faults
    if FIXED_CSV.exists():
        try:
            fixed_df = pd.read_csv(FIXED_CSV)
            fixed_df['verification_status'] = 'fixed'
            all_faults.append(fixed_df)
            logger.info(f"Loaded {len(fixed_df)} fixed faults")
        except Exception as e:
            logger.error(f"Failed to load fixed faults: {e}")
    
    if not all_faults:
        logger.warning("No verified or fixed faults found")
        return pd.DataFrame()
    
    # Combine all faults
    combined_df = pd.concat(all_faults, ignore_index=True)
    
    # Ensure all expected columns exist
    expected_cols = [
        'FullTimestamp', 'timestamp', 'description', 'tag', 'run_number',
        'ShiftLogNumber', 'ShiftLogbookURL', 'ShiftTitle', 'ShiftDateTime', 'ShiftHall',
        'FragmentLink', 'verification_status'
    ]
    
    for col in expected_cols:
        if col not in combined_df.columns:
            combined_df[col] = None
    
    # Reorder columns
    combined_df = combined_df[[col for col in expected_cols if col in combined_df.columns]]
    
    # Sort by timestamp
    if 'FullTimestamp' in combined_df.columns:
        combined_df = combined_df.sort_values('FullTimestamp')
    
    # Save final output (append to existing files)
    ALL_FAULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    if ALL_FAULTS_CSV.exists() and ALL_FAULTS_CSV.stat().st_size > 0:
        # Append to existing file (no header)
        combined_df.to_csv(ALL_FAULTS_CSV, mode='a', index=False, header=False)
        logger.info(f"Appended {len(combined_df)} verified faults to {ALL_FAULTS_CSV}")
    else:
        # Create new file with header
        combined_df.to_csv(ALL_FAULTS_CSV, mode='w', index=False, header=True)
        logger.info(f"Created {ALL_FAULTS_CSV} with {len(combined_df)} verified faults")
    
    return combined_df


def final_verification(agent: str = None) -> Optional[pd.DataFrame]:
    """
    Consolidation step - combines all verified faults.
    
    Args:
        agent: openclaw agent name (unused)
        
    Returns:
        DataFrame with all verified faults
    """
    logger.info("Starting consolidation")
    
    # Get existing faults count before consolidation
    existing_count = 0
    if ALL_FAULTS_CSV.exists() and ALL_FAULTS_CSV.stat().st_size > 0:
        try:
            existing_df = pd.read_csv(ALL_FAULTS_CSV)
            existing_count = len(existing_df)
            logger.info(f"Found {existing_count} existing faults in {ALL_FAULTS_CSV}")
        except Exception as e:
            logger.warning(f"Could not read existing faults: {e}")
    
    result = consolidate_faults(agent)
    
    # Log final count after append
    if result is not None and len(result) > 0:
        if existing_count > 0:
            logger.info(f"Total faults in {ALL_FAULTS_CSV} after append: {existing_count + len(result)}")
        else:
            logger.info(f"Total faults in {ALL_FAULTS_CSV} after creation: {len(result)}")
    
    return result


def main_function5(agent: str = None) -> Optional[pd.DataFrame]:
    """
    Main entry point for consolidation.
    
    Args:
        agent: openclaw agent name (unused)
        
    Returns:
        DataFrame with all verified faults
    """
    return final_verification(agent)
