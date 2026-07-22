"""
Caching utilities to reduce redundant API calls and improve performance.
"""
import hashlib
import json
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth


class LRUCache:
    """Simple LRU cache with TTL support."""
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.cache: Dict[str, tuple] = {}
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache if valid."""
        if key not in self.cache:
            return None
        
        value, timestamp = self.cache[key]
        
        # Check TTL
        if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
            del self.cache[key]
            return None
        
        # Move to end (most recently used)
        del self.cache[key]
        self.cache[key] = (value, timestamp)
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set item in cache."""
        # Evict oldest if at capacity
        if len(self.cache) >= self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[key] = (value, datetime.now())
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()


class CachedAPIClient:
    """
    Cached API client for JLab logbook API.
    Reduces redundant API calls by caching responses.
    """
    
    def __init__(self, base_url: str, username: str = None, password: str = None):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.cache = LRUCache(max_size=200, ttl_seconds=1800)  # 30 min TTL
        self._session = requests.Session()
        if username and password:
            self._session.auth = HTTPBasicAuth(username, password)
    
    def _make_cache_key(self, url: str, params: dict) -> str:
        """Generate cache key from URL and parameters."""
        key_data = f"{url}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, url: str, params: dict = None, use_cache: bool = True) -> Optional[dict]:
        """
        Make GET request with optional caching.
        
        Args:
            url: API endpoint URL
            params: Query parameters
            use_cache: Whether to use cache
            
        Returns:
            Response JSON or None on failure
        """
        params = params or {}
        cache_key = self._make_cache_key(url, params)
        
        # Check cache first
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached
        
        # Make request
        try:
            response = self._session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            # Cache the result
            if use_cache:
                self.cache.set(cache_key, result)
            
            return result
            
        except requests.RequestException as e:
            print(f"API request failed: {e}")
            return None
    
    def get_single_entry(self, lognumber: str) -> Optional[dict]:
        """
        Fetch a single logbook entry by number.
        
        Args:
            lognumber: Logbook entry number
            
        Returns:
            Entry data or None
        """
        url = f"{self.base_url}/entries/{lognumber}"
        return self.get(url, use_cache=True)
    
    def clear_cache(self) -> None:
        """Clear the API cache."""
        self.cache.clear()
