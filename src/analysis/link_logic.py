"""
URL fragment link creation for fault timestamps.
Creates clickable links to specific positions in shift summaries.
"""
from urllib.parse import urlparse, parse_qs, urlencode, quote


def create_text_fragment_link(url: str, timestamp: str, separator: str = ".") -> str:
    """
    Create a text fragment link for a specific timestamp in a logbook entry.
    
    Text Fragment syntax: https://web.dev/text-fragment/
    
    Args:
        url: Base URL to the logbook entry
        timestamp: Timestamp to link to (e.g., "14:30")
        separator: Separator for text fragment syntax
        
    Returns:
        URL with text fragment appended
    """
    if not url or not timestamp:
        return url
    
    try:
        parsed = urlparse(url)
        
        # Create text fragment
        # Format: #:~:text=timestamp
        # IMPORTANT: URL-encode the timestamp to handle special chars like colons
        # e.g., "14:30" becomes "14%3A30"
        fragment_text = quote(timestamp, safe='')
        
        # Add fragment to URL
        new_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}#:~:text={fragment_text}"
        
        return new_url
        
    except Exception as e:
        # Return original URL on error
        return url


def create_fragment_link_with_context(url: str, timestamp: str, context_lines: int = 2) -> str:
    """
    Create a text fragment link with surrounding context.
    
    Args:
        url: Base URL to the logbook entry
        timestamp: Timestamp to link to
        context_lines: Number of context lines to include
        
    Returns:
        URL with text fragment including context
    """
    if not url or not timestamp:
        return url
    
    try:
        parsed = urlparse(url)
        
        # Create text fragment with prefix and suffix
        # Format: #:~:text=prefix-,timestamp,suffix
        # IMPORTANT: URL-encode all parts to handle special characters
        prefix = quote("Shift", safe='')
        suffix = quote("Fault", safe='')
        timestamp_encoded = quote(timestamp, safe='')
        
        fragment = f"{prefix}-,*{timestamp_encoded}*,{suffix}"
        new_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}#:~:text={fragment}"
        
        return new_url
        
    except Exception as e:
        return url
