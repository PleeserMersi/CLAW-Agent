"""
Optimized data loading module.
Fetches shift summaries from JLab API with caching and efficient processing.
"""
import json
import time
import pandas as pd
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import (
    JLAB_LOGBOOK_BASE_URL, HALL_LOGBOOKS, DEFAULT_HALLS, EXCLUDED_LOGBOOKS,
    SEARCH_TITLE, DEFAULT_PAGE_LIMIT, API_DELAY_SECONDS,
    JLAB_USERNAME, JLAB_PASSWORD,
    SHIFT_SUMMARY_JSON, SHIFT_SUMMARY_CSV
)
from utils.cache_utils import CachedAPIClient
from utils.text_utils import html_to_text, clean_text, normalize_shift_title
from utils.logging_utils import logger


def fetch_shift_summaries(
    start_date: str,
    end_date: str,
    halls: List[str] = None,
    excluded_books: List[str] = None,
    search_title: str = None,
    username: str = None,
    password: str = None
) -> Optional[Dict[str, Any]]:
    """
    Fetch shift summaries from JLab logbook API with pagination and caching.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        halls: List of hall names to include ("hall_a", "hall_b", "hall_c", "hall_d"). 
               Default: all halls.
        excluded_books: Logbook IDs to exclude
        search_title: Title substring to search
        username: JLab username
        password: JLab password
        
    Returns:
        Combined JSON response or None
    """
    halls = halls or DEFAULT_HALLS
    excluded_books = excluded_books or EXCLUDED_LOGBOOKS
    search_title = search_title or SEARCH_TITLE
    
    # Convert hall names to logbook IDs
    logbook_ids = [HALL_LOGBOOKS[hall] for hall in halls if hall in HALL_LOGBOOKS]
    
    # Create mapping: logbook_id -> hall_name
    logbook_to_hall = {HALL_LOGBOOKS[hall]: hall for hall in halls if hall in HALL_LOGBOOKS}
    
    # Initialize cached API client
    api_client = CachedAPIClient(
        base_url=JLAB_LOGBOOK_BASE_URL,
        username=username or JLAB_USERNAME,
        password=password or JLAB_PASSWORD
    )
    
    # Prepare parameters - fetch from all selected logbooks
    all_entries = []
    current_page = 0
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 3
    
    try:
        # Fetch from each logbook separately to track which hall each entry came from
        for logbook_id in logbook_ids:
            params = {
                "startdate": start_date,
                "enddate": end_date,
                "title": search_title,
                "field": ["lognumber", "title", "created", "body"],
                "book": [logbook_id] + excluded_books,
                "page": 0
            }
            
            current_page = 0
            while True:
                params["page"] = current_page
                
                result = api_client.get(f"{JLAB_LOGBOOK_BASE_URL}/entries", params=params)
                
                if not result:
                    consecutive_failures += 1
                    logger.error(f"API request failed for {logbook_id} page {current_page} (consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})")
                    
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.error(f"\n{'='*60}")
                        logger.error(f"PIPELINE STOPPED: API fetch failed {MAX_CONSECUTIVE_FAILURES} consecutive times.")
                        logger.error(f"The JLab logbook API may be unavailable or unreachable.")
                        logger.error(f"{'='*60}\n")
                        return None
                    continue
                
                # Reset failure counter on success
                consecutive_failures = 0
                
                page_data = result.get('data', {})
                entries = page_data.get('entries', [])
                
                if not entries:
                    # Reset failure counter when we successfully reach an empty page
                    consecutive_failures = 0
                    break
                
                # Add hall information to each entry
                hall_name = logbook_to_hall.get(logbook_id, 'Unknown')
                for entry in entries:
                    entry['_hall'] = hall_name
                
                all_entries.extend(entries)
                
                total_items = int(page_data.get('totalItems', 0))
                page_count = int(page_data.get('pageCount', 0))
                
                logger.info(f"Retrieved from {logbook_id} ({hall_name}): page {current_page + 1}/{page_count} ({len(entries)} entries)")
                
                current_page += 1
                if current_page >= page_count:
                    break
                
                time.sleep(API_DELAY_SECONDS)
        
        logger.info(f"Successfully retrieved {len(all_entries)} entries from halls: {', '.join(halls)}")
        
        if not all_entries:
            return None
        
        # Construct final result
        result = {
            'stat': 'ok',
            'data': {
                'currentItems': len(all_entries),
                'totalItems': str(len(all_entries)),
                'pageLimit': DEFAULT_PAGE_LIMIT,
                'currentPage': 0,
                'pageCount': current_page,
                'entries': all_entries
            }
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error during API fetch: {e}")
        return None


def process_json_to_dataframe(
    json_data: Dict[str, Any] = None,
    json_file: Path = None,
    normalize: bool = True,
    halls: List[str] = None
) -> Optional[pd.DataFrame]:
    """
    Convert JSON shift summary data to DataFrame with efficient processing.
    
    Args:
        json_data: JSON data dictionary
        json_file: Path to JSON file
        normalize: Whether to normalize content
        halls: List of hall names (for mapping logbook IDs to hall names)
        
    Returns:
        Processed DataFrame or None
    """
    halls = halls or DEFAULT_HALLS
    
    # Create reverse mapping: logbook_id -> hall_name
    logbook_to_hall = {v: k for k, v in HALL_LOGBOOKS.items()}
    
    # Load JSON data
    if json_data is None:
        if json_file is None:
            json_file = SHIFT_SUMMARY_JSON
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON file: {e}")
            return None
    
    # Extract entries using json_normalize for efficiency
    entries = json_data.get('data', {}).get('entries', [])
    if not entries:
        return None
    
    df = pd.json_normalize(
        entries,
        sep='_',
        meta=[
            'lognumber',
            'title',
            ['created', 'string'],
            ['body', 'format'],
            ['body', 'content']
        ]
    )
    
    # Rename columns
    df = df.rename(columns={
        'lognumber': 'LogNumber',
        'title': 'Title',
        'created_string': 'Date',
        'body_format': 'Format',
        'body_content': 'Content'
    })
    
    # Add URL
    df['LogbookURL'] = df['LogNumber'].apply(lambda x: f"https://logbooks.jlab.org/entry/{x}")
    
    # Add Hall column from the _hall field added during fetch
    if '_hall' in df.columns:
        df['Hall'] = df['_hall'].str.replace('_', ' ').str.title()
        df = df.drop(columns=['_hall'])
    else:
        df['Hall'] = 'Unknown'
    
    # Normalize content in batch (vectorized where possible)
    if normalize:
        df = normalize_dataframe_content(df)
    
    # Convert dates
    try:
        df['DateTime'] = pd.to_datetime(df['Date'], errors='coerce')
    except Exception as e:
        logger.warning(f"Date conversion failed: {e}")
    
    # Reorder columns
    columns = ['LogNumber', 'LogbookURL', 'Title', 'Date', 'DateTime', 'Format', 'Content', 'Hall']
    if 'NormalizedContent' in df.columns:
        columns.append('NormalizedContent')
    
    df = df[[col for col in columns if col in df.columns]]
    
    return df


def normalize_dataframe_content(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize content column efficiently.
    
    Args:
        df: DataFrame with Content and Format columns
        
    Returns:
        DataFrame with added NormalizedContent column
    """
    def normalize_row(row):
        content = row.get('Content', '')
        format_type = row.get('Format', '')
        
        if pd.isna(content) or not content:
            return ""
        
        content = str(content)
        
        # Check if HTML
        is_html = format_type == 'html' or '<html>' in content.lower()
        
        if is_html:
            return html_to_text(content)
        else:
            return clean_text(content)
    
    # Apply normalization
    df['NormalizedContent'] = df.apply(normalize_row, axis=1)
    
    # Normalize titles
    df['Title'] = df['Title'].apply(normalize_shift_title)
    
    # Drop NaNs and duplicates in content
    df = df.dropna(subset=['Content']).drop_duplicates(subset=['Content'])
    df = df.reset_index(drop=True)
    
    return df


def main_function1(start: str, end: str, halls: List[str] = None) -> Optional[pd.DataFrame]:
    """
    Main entry point for data loading pipeline.
    
    Args:
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        halls: List of hall names to include. Default: all halls.
        
    Returns:
        Processed DataFrame or None
    """
    halls = halls or DEFAULT_HALLS
    start_time = time.time()
    
    hall_names = [h.replace('_', ' ').title() for h in halls]
    logger.info(f"Starting data loading for {start} to {end}")
    logger.info(f"Halls: {', '.join(hall_names)}")
    
    # Fetch data
    json_data = fetch_shift_summaries(start, end, halls=halls)
    
    if json_data is None:
        logger.error("No data fetched from API")
        return None
    
    # Save raw JSON
    try:
        with open(SHIFT_SUMMARY_JSON, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=4)
        logger.info(f"Saved raw data to {SHIFT_SUMMARY_JSON}")
    except Exception as e:
        logger.error(f"Failed to save JSON: {e}")
    
    # Process to DataFrame
    df = process_json_to_dataframe(json_data, halls=halls)
    
    if df is None:
        logger.error("Failed to process data to DataFrame")
        return None
    
    # Save CSV
    try:
        df.to_csv(SHIFT_SUMMARY_CSV, index=False)
        logger.info(f"Saved processed data to {SHIFT_SUMMARY_CSV}")
    except Exception as e:
        logger.error(f"Failed to save CSV: {e}")
    
    # Log statistics
    logger.info(f"Loaded {len(df)} shift summaries")
    if 'DateTime' in df.columns:
        date_range = f"{df['DateTime'].min()} to {df['DateTime'].max()}"
        logger.info(f"Date range: {date_range}")
    
    # Log hall distribution
    if 'Hall' in df.columns:
        hall_counts = df['Hall'].value_counts()
        for hall, count in hall_counts.items():
            logger.info(f"  {hall}: {count} summaries")
    
    elapsed = time.time() - start_time
    logger.info(f"Data loading completed in {elapsed:.2f} seconds")
    
    return df
