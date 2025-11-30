"""
FPL API Service
Wrapper for Fantasy Premier League API calls with caching and error handling
"""

import requests
import time
import pandas as pd
from typing import Dict, List, Optional
from functools import lru_cache
import config

# Import cache for disk-based persistence
# Note: This creates a circular import risk, so we'll use lazy import
_cache = None

def get_cache():
    """Lazy import cache to avoid circular dependency"""
    global _cache
    if _cache is None:
        from extensions import cache
        _cache = cache
    return _cache


class FPLError(Exception):
    """Custom exception for FPL API errors"""
    pass


def fetch_json(url: str, timeout: int = config.REQUEST_TIMEOUT, max_retries: int = config.MAX_RETRIES) -> Dict:
    """
    Fetch JSON data from URL with retry logic and error handling
    
    Args:
        url: API endpoint URL
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        
    Returns:
        Dict: JSON response data
        
    Raises:
        FPLError: If unable to fetch data after all retries
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise FPLError(f"Unable to fetch data from {url}: {str(e)}")
            time.sleep(2 ** attempt)  # Exponential backoff
    
    raise FPLError(f"Failed after {max_retries} attempts to fetch data from {url}")


def get_bootstrap_static_raw() -> Dict:
    """
    Get raw bootstrap-static data from FPL API
    Cached for 24 hours on disk as this data is static

    Returns:
        Dict with complete bootstrap-static data

    Raises:
        FPLError: If unable to fetch data
    """
    cache = get_cache()
    cache_key = 'bootstrap_static_raw'
    
    # Try to get from cache
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Fetch fresh data
    try:
        data = fetch_json("https://fantasy.premierleague.com/api/bootstrap-static/")
        # Store in cache with 24-hour TTL
        cache.set(cache_key, data, timeout=config.BOOTSTRAP_CACHE_TTL)
        return data
    except Exception as e:
        raise FPLError(f"Unable to fetch bootstrap data: {str(e)}")


@lru_cache(maxsize=32)
def get_bootstrap_static() -> pd.DataFrame:
    """
    Get bootstrap-static data to map player ID to names

    Returns:
        DataFrame with player information

    Raises:
        FPLError: If unable to fetch player data
    """
    try:
        data = get_bootstrap_static_raw()
        players = []

        for player in data['elements']:
            players.append({
                'id': player['id'],
                'web_name': player['web_name'],
                'first_name': player['first_name'],
                'second_name': player['second_name'],
                'team': player['team'],
                'element_type': player['element_type'],
                'full_name': f"{player['first_name']} {player['second_name']}"
            })

        return pd.DataFrame(players)
    except Exception as e:
        raise FPLError(f"Unable to fetch player data: {str(e)}")


def get_current_gw() -> int:
    """
    Get current gameweek (latest in-progress or finished GW) from FPL API
    
    Priority:
    1. Find GW with started fixtures (in progress)
    2. Find latest finished GW
    3. Find current GW by is_current flag
    4. Find next GW and subtract 1
    
    Returns:
        Current gameweek number
    """
    try:
        data = get_bootstrap_static_raw()
        events = data.get('events', [])
        
        # Priority 1: Find GW with started fixtures (most accurate for in-progress GW)
        # Check recent GWs in reverse order (most recent first)
        for event in sorted(events, key=lambda x: x['id'], reverse=True):
            gw_id = event['id']
            try:
                # Check if any fixture in this GW has started
                fixtures_url = f"https://fantasy.premierleague.com/api/fixtures/?event={gw_id}"
                fixtures_data = fetch_json(fixtures_url)
                
                # If any fixture has started, this is the current GW
                if any(fixture.get('started', False) for fixture in fixtures_data):
                    return gw_id
            except:
                # Continue to next GW if fixtures check fails
                continue
        
        # Priority 2: Find the latest finished gameweek (fallback)
        finished_gw = 0
        for event in events:
            if event.get('finished', False):
                finished_gw = max(finished_gw, event['id'])
        
        if finished_gw > 0:
            return finished_gw
        
        # Priority 3: If no finished GW, find current GW by flag
        for event in events:
            if event.get('is_current', False):
                return event['id']
        
        # Priority 4: If no current GW, find next GW
        for event in events:
            if event.get('is_next', False):
                return max(1, event['id'] - 1)
        
        return 1  # Ultimate fallback
    except:
        return 1  # Default fallback


def get_league_entries(league_id: int, phase: int, pages: List[int]) -> pd.DataFrame:
    """
    Get list of entries in league with pagination support
    
    Args:
        league_id: FPL league ID
        phase: League phase number
        pages: List of page numbers to fetch
        
    Returns:
        DataFrame with league entries
        
    Raises:
        FPLError: If unable to fetch any entries data
    """
    all_entries = []
    
    for page in pages:
        try:
            url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/?page_standings={page}&phase={phase}"
            data = fetch_json(url)
            
            if 'standings' not in data or 'results' not in data['standings']:
                print(f"Warning: No data found for page {page}")
                continue
            
            for entry in data['standings']['results']:
                all_entries.append({
                    'Team_ID': entry['entry'],
                    'Manager': entry['player_name'],
                    'Team': entry['entry_name'],
                    'Rank': entry.get('rank', 0),
                    'Total': entry.get('total', 0)
                })
            
            time.sleep(config.REQUEST_DELAY)  # Delay to avoid rate limit
            
        except Exception as e:
            print(f"Error fetching page {page}: {str(e)}")
            continue
    
    if not all_entries:
        raise FPLError("Unable to fetch any entries data")
    
    return pd.DataFrame(all_entries)


def get_all_league_entries(league_id: int, phase: int) -> pd.DataFrame:
    """
    Get all entries in league by automatically discovering all pages
    Cached for 1 hour on disk as league standings change relatively slowly
    
    Args:
        league_id: FPL league ID
        phase: League phase number
        
    Returns:
        DataFrame with all league entries
        
    Raises:
        FPLError: If unable to fetch any entries data
    """
    cache = get_cache()
    cache_key = f'league_entries_{league_id}_{phase}'
    
    # Try to get from cache
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Fetch fresh data
    all_entries = []
    page = 1
    max_pages = 100  # Safety limit to prevent infinite loop
    
    while page <= max_pages:
        try:
            url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/?page_standings={page}&phase={phase}"
            data = fetch_json(url)
            
            if 'standings' not in data or 'results' not in data['standings']:
                # No more data available
                break
            
            results = data['standings']['results']
            if not results:
                # Empty page, no more data
                break
            
            for entry in results:
                all_entries.append({
                    'Team_ID': entry['entry'],
                    'Manager': entry['player_name'],
                    'Team': entry['entry_name'],
                    'Rank': entry.get('rank', 0),
                    'Total': entry.get('total', 0)
                })
            
            # Check if this is the last page
            has_next = data['standings'].get('has_next', False)
            if not has_next:
                break
            
            page += 1
            time.sleep(config.REQUEST_DELAY)  # Delay to avoid rate limit
            
        except Exception as e:
            print(f"Warning: Error fetching page {page}: {str(e)}")
            # Try next page in case of temporary error
            page += 1
            continue
    
    if not all_entries:
        raise FPLError("Unable to fetch any entries data")
    
    df = pd.DataFrame(all_entries)
    
    # Store in cache with 1-hour TTL
    cache.set(cache_key, df, timeout=config.LEAGUE_CACHE_TTL)
    
    return df


def get_entry_gw_picks(entry_id: int, gw: int) -> Optional[Dict]:
    """
    Get picks and entry history for a specific entry and GW
    
    Args:
        entry_id: FPL team entry ID
        gw: Gameweek number
        
    Returns:
        Dict with picks and entry history data, or None if error
    """
    try:
        url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/event/{gw}/picks/"
        data = fetch_json(url)
        
        # Check if entry_history exists
        if 'entry_history' not in data:
            # Fallback: get from history endpoint
            history_url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
            history_data = fetch_json(history_url)
            
            # Find corresponding GW in history
            for event in history_data.get('current', []):
                if event['event'] == gw:
                    data['entry_history'] = event
                    break
        
        return data
    except Exception as e:
        print(f"Warning: Unable to fetch data for entry {entry_id}, GW {gw}: {str(e)}")
        return None


def get_entry_history(entry_id: int) -> Optional[Dict]:
    """
    Get complete entry history for all gameweeks - optimized single API call
    Cached for 15 minutes on disk as GW data updates frequently
    
    Args:
        entry_id: FPL team entry ID
        
    Returns:
        Dict with complete history data, or None if error
    """
    cache = get_cache()
    cache_key = f'entry_history_{entry_id}'
    
    # Try to get from cache
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Fetch fresh data
    try:
        url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
        data = fetch_json(url)
        
        # Store in cache with 15-minute TTL
        cache.set(cache_key, data, timeout=config.GW_DATA_CACHE_TTL)
        
        return data
    except Exception as e:
        print(f"Warning: Unable to fetch history data for entry {entry_id}: {str(e)}")
        return None


def get_entry_transfers(entry_id: int) -> Optional[List]:
    """
    Get transfer history for a specific entry
    Cached for 15 minutes on disk
    
    Args:
        entry_id: FPL team entry ID
        
    Returns:
        List of transfer data, or None if error
    """
    cache = get_cache()
    cache_key = f'entry_transfers_{entry_id}'
    
    # Try to get from cache
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Fetch fresh data
    try:
        url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/transfers/"
        data = fetch_json(url)
        
        # Store in cache with 15-minute TTL
        cache.set(cache_key, data, timeout=config.GW_DATA_CACHE_TTL)
        
        return data
    except Exception as e:
        print(f"Warning: Unable to fetch transfer data for entry {entry_id}: {str(e)}")
        return None


@lru_cache(maxsize=1024)
def get_player_history(element_id: int) -> Dict:
    """Get full element summary for a player, cached in memory.

    This avoids hitting the FPL ``element-summary`` endpoint repeatedly for the
    same player, which is critical for heavy features like transfer history
    that may need points for the same player across many league entries.
    """
    try:
        url = f"https://fantasy.premierleague.com/api/element-summary/{element_id}/"
        return fetch_json(url)
    except Exception as e:
        # Log and fall back to empty data; callers will treat missing history
        # as zero points rather than failing the whole request.
        print(f"Warning: Unable to fetch history for player {element_id}: {str(e)}")
        return {}


def get_player_gw_points(element_id: int, gw: int) -> int:
    """Get player points for a specific gameweek.

    Uses :func:`get_player_history` under the hood so each player's season
    data is fetched at most once per process. This significantly reduces the
    number of external API calls when building transfer history and other
    stats that need per-GW player points.
    """
    try:
        data = get_player_history(element_id)

        # Find the specific gameweek in history
        for event in data.get('history', []):
            if event.get('round') == gw:
                return event.get('total_points', 0)

        return 0
    except Exception:
        return 0
