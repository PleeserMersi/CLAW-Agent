"""
Optimized text processing utilities.
Includes regex-based timestamp parsing and text normalization.
"""
import re
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional


def html_to_text(html_content: str) -> str:
    """
    Convert HTML content to plain text.
    
    Args:
        html_content: HTML string
        
    Returns:
        Plain text extracted from HTML
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    text = soup.get_text(separator=' ', strip=True)
    
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text


def clean_text(text: str) -> str:
    """
    Clean plain text by normalizing whitespace.
    
    Args:
        text: Input text
        
    Returns:
        Cleaned text
    """
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def normalize_shift_title(title: str) -> str:
    """
    Normalize shift summary title.
    
    Args:
        title: Original title
        
    Returns:
        Normalized title
    """
    if not title:
        return ""
    
    # Remove common prefixes
    title = re.sub(r'^Shift Summary:\s*', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^Hall B Shift Summary:\s*', '', title, flags=re.IGNORECASE)
    
    return title.strip()


def normalize_timestamp(timestamp: str) -> Optional[str]:
    """
    Normalize timestamp to HH:MM 24-hour format.
    
    Uses efficient regex-based parsing instead of multiple string replacements.
    Supports both 12-hour (with am/pm) and 24-hour formats.
    Handles 24:00 by returning None (should be handled by caller with date rollover).
    
    Args:
        timestamp: Raw timestamp string
        
    Returns:
        Normalized timestamp in HH:MM format, or None if invalid or 24:00
    """
    if not timestamp:
        return None
    
    # Clean the timestamp
    clean = timestamp.strip()
    
    # Remove unwanted characters but keep digits, colons, spaces, am/pm
    clean = re.sub(r'[^0-9:\sapm\-\.]', '', clean, flags=re.IGNORECASE)
    
    # Check if it's already in 24-hour format (HH:MM)
    match_24h = re.match(r'^([0-2]?[0-9]):([0-5][0-9])$', clean)
    if match_24h:
        hour = int(match_24h.group(1))
        minute = int(match_24h.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
        # Handle 24:00 case - return None to signal day rollover needed
        if hour == 24 and minute == 0:
            return None
        return None
    
    # Try to match 12-hour format with am/pm
    match = re.match(r'^(\d{1,2}):?(\d{2})?\s*(am|pm)$', clean, flags=re.IGNORECASE)
    
    if not match:
        return None
    
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    ampm = match.group(3)
    
    # Validate hour and minute
    if hour < 1 or hour > 12:
        return None
    if minute < 0 or minute > 59:
        return None
    
    # Convert to 24-hour format
    if ampm:
        ampm = ampm.lower()
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
    
    return f"{hour:02d}:{minute:02d}"


def parse_timestamp_to_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """
    Parse date and time strings into a datetime object.
    
    Handles 24:00 by incrementing the date by one day.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        time_str: Time in HH:MM format (can be 24:00)
        
    Returns:
        datetime object or None
    """
    try:
        date_part = datetime.strptime(date_str, "%Y-%m-%d")
        
        # Handle 24:00 case - increment date and set time to 00:00
        if time_str == "24:00":
            from datetime import timedelta
            date_part = date_part + timedelta(days=1)
            return date_part.replace(hour=0, minute=0)
        
        time_part = datetime.strptime(time_str, "%H:%M")
        
        return date_part.replace(hour=time_part.hour, minute=time_part.minute)
    except ValueError:
        return None


def extract_time_from_text(text: str) -> Optional[str]:
    """
    Extract a time reference from text.
    
    Args:
        text: Text to search
        
    Returns:
        Extracted time in HH:MM format, or None
    """
    # Match various time patterns
    patterns = [
        r'(\d{1,2}):(\d{2})\s*(am|pm)?',  # 14:30 or 2:30 pm
        r'(\d{1,2})\s*(am|pm)',            # 2pm or 2 pm
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            if match.group(3):  # Has am/pm
                hour = int(match.group(1))
                minute = int(match.group(2))
                ampm = match.group(3).lower()
                
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                return f"{hour:02d}:{minute:02d}"
            else:  # 24-hour format
                return f"{match.group(1)}:{match.group(2)}"
    
    return None
