import streamlit as st
import pandas as pd
import requests
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import plotly.express as px
import plotly.graph_objects as go
import config

# Page configuration
st.set_page_config(
    page_title=config.PAGE_TITLE,
    page_icon=config.PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

class FPLError(Exception):
    """Custom exception for FPL API errors"""
    pass

def show_temporary_message(message: str, message_type: str = "success"):
    """
    Show a temporary message - simplified version that just shows the message
    For Streamlit, we'll rely on the natural flow to clear messages
    """
    if message_type == "success":
        st.success(message)
    elif message_type == "warning":
        # Only show critical warnings, suppress routine ones
        if "404 Client Error" not in message and "Unable to fetch data for entry" not in message:
            st.warning(message)
    elif message_type == "error":
        st.error(message)
    elif message_type == "info":
        st.info(message)

def clear_all_cache():
    """
    Clear all cached data and session state
    """
    # Clear Streamlit cache
    st.cache_data.clear()

    # Clear session state data
    cache_keys = ['entries_df', 'bootstrap_df', 'gw_range', 'gw_points_df', 'gw_display_df', 'top_picks_df', 'data_loaded_at']
    for key in cache_keys:
        if key in st.session_state:
            del st.session_state[key]

@st.cache_data(ttl=config.API_CACHE_TTL)
def fetch_json(url: str, timeout: int = config.REQUEST_TIMEOUT, max_retries: int = config.MAX_RETRIES) -> Dict:
    """
    Fetch JSON data from URL with retry logic and error handling
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

@st.cache_data(ttl=config.BOOTSTRAP_CACHE_TTL)
def get_bootstrap_static() -> pd.DataFrame:
    """
    Get bootstrap-static data to map player ID to names
    """
    try:
        data = fetch_json("https://fantasy.premierleague.com/api/bootstrap-static/")
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

@st.cache_data(ttl=config.API_CACHE_TTL)
def get_league_entries(league_id: int, phase: int, pages: List[int]) -> pd.DataFrame:
    """
    Get list of entries in league with pagination support
    """
    all_entries = []

    for page in pages:
        try:
            url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/?page_standings={page}&phase={phase}"
            data = fetch_json(url)

            if 'standings' not in data or 'results' not in data['standings']:
                st.warning(f"No data found for page {page}")
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
            st.error(f"Error fetching page {page}: {str(e)}")
            continue

    if not all_entries:
        raise FPLError("Unable to fetch any entries data")

    return pd.DataFrame(all_entries)

@st.cache_data(ttl=config.API_CACHE_TTL)
def get_all_league_entries(league_id: int, phase: int) -> pd.DataFrame:
    """
    Get all entries in league by automatically discovering all pages
    """
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
            show_temporary_message(f"Error fetching page {page}: {str(e)}", "warning")
            # Try next page in case of temporary error
            page += 1
            continue

    if not all_entries:
        raise FPLError("Unable to fetch any entries data")

    # Create temporary message that will be cleared by subsequent operations
    status_placeholder = st.empty()
    status_placeholder.success(f"Loaded {len(all_entries)} entries from {page-1} pages")
    return pd.DataFrame(all_entries)

def get_entry_gw_picks(entry_id: int, gw: int) -> Optional[Dict]:
    """
    Get picks and entry history for a specific entry and GW
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
        show_temporary_message(f"Unable to fetch data for entry {entry_id}, GW {gw}: {str(e)}", "warning")
        return None

def parse_month_mapping(mapping_str: str) -> Dict[int, int]:
    """
    Parse month mapping string to dict {gw: month}
    Example: "1-4,5-9,10-13" -> {1:1, 2:1, 3:1, 4:1, 5:2, 6:2, ...}
    """
    gw_to_month = {}

    try:
        ranges = mapping_str.split(',')
        for month_idx, range_str in enumerate(ranges, 1):
            if '-' in range_str:
                start, end = map(int, range_str.strip().split('-'))
                for gw in range(start, end + 1):
                    gw_to_month[gw] = month_idx
            else:
                gw = int(range_str.strip())
                gw_to_month[gw] = month_idx
    except Exception as e:
        st.error(f"Error parsing month mapping: {str(e)}")
        return {}

    return gw_to_month

def build_gw_points_table(entries_df: pd.DataFrame, gw_range: List[int], max_entries: Optional[int] = None) -> pd.DataFrame:
    """
    Build gameweek points table for all entries
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)

    results = []
    total_requests = len(entries_df) * len(gw_range)

    # Progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_info = {}
        for _, entry in entries_df.iterrows():
            for gw in gw_range:
                future = executor.submit(get_entry_gw_picks, entry['Team_ID'], gw)
                future_to_info[future] = (entry['Team_ID'], entry['Manager'], entry['Team'], gw)

        # Collect results
        completed = 0
        for future in as_completed(future_to_info):
            team_id, manager, team, gw = future_to_info[future]
            completed += 1

            # Update progress
            progress = completed / total_requests
            progress_bar.progress(progress)
            status_text.text(f"Fetching data: {completed}/{total_requests} ({progress:.1%})")

            try:
                data = future.result()
                if data and 'entry_history' in data:
                    history = data['entry_history']
                    results.append({
                        'Team_ID': team_id,
                        'Manager': manager,
                        'Team': team,
                        'GW': gw,
                        'Points': history.get('points', 0),
                        'Total_Points': history.get('total_points', 0),
                        'Transfers': history.get('event_transfers', 0),
                        'picks': data.get('picks', [])
                    })
                else:
                    # Add row with default values if no data
                    results.append({
                        'Team_ID': team_id,
                        'Manager': manager,
                        'Team': team,
                        'GW': gw,
                        'Points': 0,
                        'Total_Points': 0,
                        'Transfers': 0,
                        'picks': []
                    })
            except Exception as e:
                show_temporary_message(f"Error processing entry {team_id}, GW {gw}: {str(e)}", "warning")
                continue

            # Small delay to avoid rate limit
            time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)

    progress_bar.empty()
    status_text.empty()

    if not results:
        raise FPLError("Unable to fetch points data for any entry")

    return pd.DataFrame(results)

def build_month_points_table(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Build month points table from GW data (excluding incomplete months)
    """
    # Add month column to dataframe
    gw_points_df['Month'] = gw_points_df['GW'].map(month_mapping)

    # Remove GWs not in mapping
    month_df = gw_points_df.dropna(subset=['Month'])

    # Filter out incomplete months (where the last GW of the month has no points > 0)
    complete_months = []
    for month in month_df['Month'].unique():
        month_gws = [gw for gw, m in month_mapping.items() if m == month]
        if month_gws:
            last_gw_of_month = max(month_gws)
            last_gw_data = gw_points_df[gw_points_df['GW'] == last_gw_of_month]
            # Include month only if the last GW has been played (has points > 0)
            if not last_gw_data.empty and (last_gw_data['Points'] > 0).any():
                complete_months.append(month)

    # Filter data to include only complete months
    month_df = month_df[month_df['Month'].isin(complete_months)]

    if month_df.empty:
        return pd.DataFrame(columns=['Team_ID', 'Manager', 'Team', 'Total'])

    # Group by entry and month, sum points
    month_summary = month_df.groupby(['Team_ID', 'Manager', 'Team', 'Month']).agg({
        'Points': 'sum',
        'Transfers': 'sum'
    }).reset_index()

    # Pivot to have column for each month
    pivot_points = month_summary.pivot_table(
        index=['Team_ID', 'Manager', 'Team'],
        columns='Month',
        values='Points',
        fill_value=0
    )

    # Create column names for months
    month_cols = [f"Month_{int(col)}" for col in pivot_points.columns]
    pivot_points.columns = month_cols

    # Add total column
    pivot_points['Total'] = pivot_points.sum(axis=1)

    # Reset index for export
    result = pivot_points.reset_index()

    return result

def build_month_points_table_full(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Build month points table from GW data (including all weeks, even with 0 points)
    This is used for Month Points tab to show complete monthly statistics
    """
    # Add month column to dataframe
    gw_points_df['Month'] = gw_points_df['GW'].map(month_mapping)

    # Remove GWs not in mapping
    month_df = gw_points_df.dropna(subset=['Month'])

    if month_df.empty:
        return pd.DataFrame(columns=['Team_ID', 'Manager', 'Team', 'Total'])

    # Group by entry and month, sum points (including 0 points)
    month_summary = month_df.groupby(['Team_ID', 'Manager', 'Team', 'Month']).agg({
        'Points': 'sum',
        'Transfers': 'sum'
    }).reset_index()

    # Pivot to have column for each month
    pivot_points = month_summary.pivot_table(
        index=['Team_ID', 'Manager', 'Team'],
        columns='Month',
        values='Points',
        fill_value=0
    )

    # Create column names for months
    month_cols = [f"Month_{int(col)}" for col in pivot_points.columns]
    pivot_points.columns = month_cols

    # Add total column
    pivot_points['Total'] = pivot_points.sum(axis=1)

    # Reset index for export
    result = pivot_points.reset_index()

    # Add Rank column based on Total points (descending)
    result = result.sort_values('Total', ascending=False)
    result['Rank'] = range(1, len(result) + 1)

    # Reorder columns to have Rank first
    cols = ['Rank', 'Team_ID', 'Manager', 'Team'] + [col for col in result.columns if col.startswith('Month_')] + ['Total']
    result = result[cols]

    return result

def compute_top_picks(entries_df: pd.DataFrame, gw_range: List[int], bootstrap_df: pd.DataFrame,
                     max_entries: Optional[int] = None) -> pd.DataFrame:
    """
    Calculate top 5 most picked players
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)

    # Get picks data from GW points table
    gw_data = build_gw_points_table(entries_df, gw_range, max_entries)

    # Count picks for each player
    player_counts = {}
    total_entries = len(entries_df)

    for _, row in gw_data.iterrows():
        picks = row['picks']
        if picks:
            for pick in picks:
                element_id = pick.get('element')
                if element_id:
                    player_counts[element_id] = player_counts.get(element_id, 0) + 1

    # Convert to DataFrame and merge with bootstrap data
    if not player_counts:
        return pd.DataFrame(columns=['Player', 'Times_Picked', 'Percent_Of_Entries'])

    picks_df = pd.DataFrame([
        {'element_id': player_id, 'times_picked': count}
        for player_id, count in player_counts.items()
    ])

    # Merge with bootstrap data to get player names
    result = picks_df.merge(
        bootstrap_df[['id', 'web_name', 'full_name']],
        left_on='element_id',
        right_on='id',
        how='left'
    )

    # Calculate percentage
    result['percent_of_entries'] = (result['times_picked'] / (total_entries * len(gw_range))) * 100

    # Sort and get top 5
    result = result.sort_values('times_picked', ascending=False).head(5)

    # Format output
    result = result[['web_name', 'times_picked', 'percent_of_entries']].copy()
    result.columns = ['Player', 'Times_Picked', 'Percent_Of_Entries']
    result['Percent_Of_Entries'] = result['Percent_Of_Entries'].round(1)

    return result

def get_current_gw() -> int:
    """
    Get current gameweek from FPL API
    """
    try:
        data = fetch_json("https://fantasy.premierleague.com/api/bootstrap-static/")
        events = data.get('events', [])

        # Find current gameweek (is_current = True or is_next = True)
        for event in events:
            if event.get('is_current', False):
                return event['id']

        # If no current GW found, find next GW
        for event in events:
            if event.get('is_next', False):
                return event['id']

        # Fallback to first unfinished GW
        for event in events:
            if not event.get('finished', False):
                return event['id']

        return 1  # Ultimate fallback
    except:
        return 1  # Default fallback

def get_current_month(gw: int, month_mapping: Dict[int, int]) -> int:
    """
    Get current month based on current GW and month mapping
    """
    return month_mapping.get(gw, 1)

@st.cache_data(ttl=config.API_CACHE_TTL)
def get_current_gameweek_range(entries_df: pd.DataFrame) -> List[int]:
    """
    Automatically determine the current gameweek range by checking which weeks have actual points
    Returns range from GW1 to the last week where at least one player has points > 0
    """
    if entries_df.empty:
        return [1]

    max_gw_to_check = 38  # Maximum possible gameweeks in a season
    current_gw_end = 1

    # Sample a few entries to check for actual gameweek data
    sample_entries = entries_df.head(min(5, len(entries_df)))

    with st.spinner("Determining current gameweek range..."):
        for gw in range(1, max_gw_to_check + 1):
            has_points = False

            # Check if any of the sample entries have points > 0 for this GW
            for _, entry in sample_entries.iterrows():
                try:
                    data = get_entry_gw_picks(entry['Team_ID'], gw)
                    if data and 'entry_history' in data:
                        points = data['entry_history'].get('points', 0)
                        if points > 0:
                            has_points = True
                            break
                except:
                    continue

            if has_points:
                current_gw_end = gw
            else:
                # If no points found for this GW, we've likely reached the current week
                # Check one more GW to be sure
                if gw > current_gw_end:
                    break

            # Small delay to avoid rate limiting
            time.sleep(config.REQUEST_DELAY / 2)

    gw_range = list(range(1, current_gw_end + 1))
    # Create temporary message that will be cleared by subsequent operations
    status_placeholder = st.empty()
    status_placeholder.success(f"Auto-detected gameweek range: GW1 to GW{current_gw_end}")

    return gw_range

def create_ranking_table(data_df: pd.DataFrame, score_column: str, has_transfers: bool = False) -> pd.DataFrame:
    """
    Create ranking table with medals for top 3
    Priority 1: Higher points = higher rank
    Priority 2: If same points, lower transfers = higher rank
    Same points + same transfers = same rank (tied medals)
    """
    if has_transfers and 'Transfers' in data_df.columns:
        # Sort by Points (descending) then by Transfers (ascending)
        ranked_df = data_df.sort_values(['Points', 'Transfers'], ascending=[False, True]).reset_index(drop=True)

        # Create ranking with ties handling
        ranked_df['Rank'] = 1
        current_rank = 1

        for i in range(1, len(ranked_df)):
            prev_points = ranked_df.loc[i-1, 'Points']
            prev_transfers = ranked_df.loc[i-1, 'Transfers']
            curr_points = ranked_df.loc[i, 'Points']
            curr_transfers = ranked_df.loc[i, 'Transfers']

            # If different points or different transfers, increment rank
            if curr_points != prev_points or curr_transfers != prev_transfers:
                current_rank = i + 1

            ranked_df.loc[i, 'Rank'] = current_rank
    else:
        # Sort by score descending only
        ranked_df = data_df.sort_values(score_column, ascending=False).reset_index(drop=True)

        # Create ranking with ties handling for points only
        ranked_df['Rank'] = 1
        current_rank = 1

        for i in range(1, len(ranked_df)):
            prev_score = ranked_df.loc[i-1, score_column]
            curr_score = ranked_df.loc[i, score_column]

            # If different score, increment rank
            if curr_score != prev_score:
                current_rank = i + 1

            ranked_df.loc[i, 'Rank'] = current_rank

    # Add medal column with tie handling
    def get_medal(rank):
        if rank <= 3:
            if rank == 1:
                return "🥇"
            elif rank == 2:
                return "🥈"
            elif rank == 3:
                return "🥉"
        return ""

    ranked_df['Medal'] = ranked_df['Rank'].apply(get_medal)

    # Reorder columns to put Medal and Rank first
    cols = ['Medal', 'Rank'] + [col for col in ranked_df.columns if col not in ['Medal', 'Rank']]
    ranked_df = ranked_df[cols]

    return ranked_df

def build_weekly_ranking(gw_points_df: pd.DataFrame, selected_gw: int) -> pd.DataFrame:
    """
    Build weekly ranking for selected GW (excluding unplayed weeks with 0 points)
    """
    # Filter for selected GW
    gw_data = gw_points_df[gw_points_df['GW'] == selected_gw].copy()

    if gw_data.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Filter out unplayed weeks (points = 0)
    gw_data = gw_data[gw_data['Points'] > 0]

    if gw_data.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Select relevant columns
    ranking_data = gw_data[['Manager', 'Team', 'Points', 'Transfers']].copy()

    # Create ranking table with transfer consideration
    ranked_df = create_ranking_table(ranking_data, 'Points', has_transfers=True)

    return ranked_df

def build_monthly_ranking(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int], selected_month: int) -> pd.DataFrame:
    """
    Build monthly ranking for selected month with transfers (excluding incomplete months)
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Filter GWs for selected month
    month_gws = [gw for gw, month in month_mapping.items() if month == selected_month]

    if not month_gws:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Check if the last GW of the month has been played (has points > 0)
    last_gw_of_month = max(month_gws)
    last_gw_data = gw_points_df[gw_points_df['GW'] == last_gw_of_month]

    # If the last GW of the month has no points > 0, consider the month incomplete
    if last_gw_data.empty or not (last_gw_data['Points'] > 0).any():
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Filter data for selected month GWs
    month_data = gw_points_df[gw_points_df['GW'].isin(month_gws)].copy()

    if month_data.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Group by team and sum points and transfers
    monthly_summary = month_data.groupby(['Team_ID', 'Manager', 'Team']).agg({
        'Points': 'sum',
        'Transfers': 'sum'
    }).reset_index()

    # Select relevant columns for ranking
    ranking_data = monthly_summary[['Manager', 'Team', 'Points', 'Transfers']].copy()

    # Create ranking table with transfer consideration
    ranked_df = create_ranking_table(ranking_data, 'Points', has_transfers=True)

    return ranked_df

def build_monthly_ranking_full(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int], selected_month: int) -> pd.DataFrame:
    """
    Build monthly ranking for selected month with transfers (including all weeks, even with 0 points)
    This is used for Rankings tab to show complete monthly rankings
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Filter GWs for selected month
    month_gws = [gw for gw, month in month_mapping.items() if month == selected_month]

    if not month_gws:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Filter data for selected month GWs (including weeks with 0 points)
    month_data = gw_points_df[gw_points_df['GW'].isin(month_gws)].copy()

    if month_data.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers'])

    # Group by team and sum points and transfers
    monthly_summary = month_data.groupby(['Team_ID', 'Manager', 'Team']).agg({
        'Points': 'sum',
        'Transfers': 'sum'
    }).reset_index()

    # Select relevant columns for ranking
    ranking_data = monthly_summary[['Manager', 'Team', 'Points', 'Transfers']].copy()

    # Create ranking table with transfer consideration
    ranked_df = create_ranking_table(ranking_data, 'Points', has_transfers=True)

    return ranked_df

def calculate_awards_statistics(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Calculate awards statistics for all managers
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['Manager', 'Team', 'Weekly_Wins', 'Monthly_Wins', 'Total_Awards'])

    # Get unique managers
    managers = gw_points_df[['Team_ID', 'Manager', 'Team']].drop_duplicates()

    # Initialize awards counter
    awards_data = []
    for _, manager in managers.iterrows():
        awards_data.append({
            'Team_ID': manager['Team_ID'],
            'Manager': manager['Manager'],
            'Team': manager['Team'],
            'Weekly_Wins': 0,
            'Monthly_Wins': 0
        })

    awards_df = pd.DataFrame(awards_data)

    # Calculate weekly wins (1st place in each GW)
    available_gws = sorted(gw_points_df['GW'].unique())

    for gw in available_gws:
        weekly_ranking = build_weekly_ranking(gw_points_df, gw)
        if not weekly_ranking.empty:
            # Get all rank 1 winners (handle ties)
            winners = weekly_ranking[weekly_ranking['Rank'] == 1]
            for _, winner in winners.iterrows():
                manager_name = winner['Manager']
                awards_df.loc[awards_df['Manager'] == manager_name, 'Weekly_Wins'] += 1

    # Calculate monthly wins (1st place in each month)
    available_months = sorted(set(month_mapping.values()))

    for month in available_months:
        monthly_ranking = build_monthly_ranking(gw_points_df, month_mapping, month)
        if not monthly_ranking.empty:
            # Get all rank 1 winners (handle ties)
            winners = monthly_ranking[monthly_ranking['Rank'] == 1]
            for _, winner in winners.iterrows():
                manager_name = winner['Manager']
                awards_df.loc[awards_df['Manager'] == manager_name, 'Monthly_Wins'] += 1

    # Calculate total awards
    awards_df['Total_Awards'] = awards_df['Weekly_Wins'] + awards_df['Monthly_Wins']

    # Sort by total awards descending, then by weekly wins, then by monthly wins
    awards_df = awards_df.sort_values(['Total_Awards', 'Weekly_Wins', 'Monthly_Wins'],
                                     ascending=[False, False, False]).reset_index(drop=True)

    # Add rank
    awards_df['Rank'] = range(1, len(awards_df) + 1)

    # Add medal for top 3
    def get_award_medal(rank):
        if rank == 1:
            return "🏆"
        elif rank == 2:
            return "🥈"
        elif rank == 3:
            return "🥉"
        else:
            return ""

    awards_df['Medal'] = awards_df['Rank'].apply(get_award_medal)

    # Reorder columns
    cols = ['Medal', 'Rank', 'Manager', 'Team', 'Weekly_Wins', 'Monthly_Wins', 'Total_Awards']
    awards_df = awards_df[cols]

    return awards_df

def create_download_button(df: pd.DataFrame, filename: str, button_text: str, key: str = None):
    """
    Create download button for CSV
    """
    csv = df.to_csv(index=False)
    st.download_button(
        label=button_text,
        data=csv,
        file_name=filename,
        mime='text/csv',
        key=key
    )

def main():
    """
    Main function containing Streamlit UI
    """
    st.title("⚽ RSC Fantasy League")
    st.markdown("Fantasy Premier League League Data Analysis")

    # Sidebar for options
    st.sidebar.header("⚙️ Configuration")

    # League settings
    league_id = st.sidebar.number_input(
        "League ID",
        value=config.DEFAULT_LEAGUE_ID,
        min_value=1,
        help="ID of the league to analyze"
    )

    phase = st.sidebar.number_input(
        "Phase",
        value=config.DEFAULT_PHASE,
        min_value=1,
        help="League phase (usually 1)"
    )

    # Pagination is now automatic - no manual settings needed

    # Gameweek range is now automatic - no manual settings needed

    # Month mapping is now automatic from config - no manual settings needed
    month_mapping_str = config.DEFAULT_MONTH_MAPPING

    # Performance settings (hidden from UI but set to default)
    max_entries = None  # No limit by default

    # Data refresh control
    st.sidebar.markdown("---")
    # st.sidebar.subheader("🔄 Data Management")

    # Show cache status
    if 'data_loaded_at' in st.session_state:
        load_time = time.time() - st.session_state.data_loaded_at
        if load_time < 60:
            time_str = f"{load_time:.0f} seconds ago"
        elif load_time < 3600:
            time_str = f"{load_time/60:.0f} minutes ago"
        else:
            time_str = f"{load_time/3600:.1f} hours ago"
        st.sidebar.info(f"📊 Data loaded: {time_str}")

    refresh_data = st.sidebar.button("🔄 Refresh Data", type="secondary", help="Reload all data from FPL API")

    # Load data logic - auto-load first time or when refresh button is clicked
    should_load_data = ('entries_df' not in st.session_state) or refresh_data

    if should_load_data:
        # Clear cache if refreshing
        if refresh_data:
            clear_all_cache()

        try:
            # Parse month mapping
            month_mapping = parse_month_mapping(month_mapping_str)
            if not month_mapping:
                st.error("Invalid month mapping")
                return

            # Load bootstrap data (cached)
            with st.spinner("Loading player data..."):
                bootstrap_df = get_bootstrap_static()

            # Load league entries (cached, auto-discover all pages)
            with st.spinner("Loading entries list..."):
                entries_df = get_all_league_entries(league_id, phase)

            if entries_df.empty:
                st.error("No entries found")
                return

            # Auto-determine gameweek range (cached)
            gw_range = get_current_gameweek_range(entries_df)

            # Store data in session state
            st.session_state.bootstrap_df = bootstrap_df
            st.session_state.entries_df = entries_df
            st.session_state.gw_range = gw_range
            st.session_state.month_mapping = month_mapping
            st.session_state.max_entries = max_entries
            st.session_state.league_id = league_id
            st.session_state.data_loaded_at = time.time()  # Track when data was loaded

            if refresh_data:
                show_temporary_message("Data refreshed successfully!", "success")
            else:
                # First time loading
                show_temporary_message("Data loaded and cached for faster access!", "info")

        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
            return
    else:
        # Update session state with current settings if data already loaded
        # GW range is auto-determined, so we keep the existing one
        # Month mapping is from config, so we keep the existing one
        st.session_state.max_entries = max_entries

    # Display data if loaded
    if 'entries_df' in st.session_state:
        entries_df = st.session_state.entries_df
        bootstrap_df = st.session_state.bootstrap_df
        gw_range = st.session_state.gw_range
        month_mapping = st.session_state.month_mapping
        max_entries = st.session_state.max_entries
        league_id = st.session_state.league_id

        # Add CSS for table styling
        st.markdown("""
        <style>
        .dataframe th {
            background-color: #f0f2f6 !important;
            color: #262730 !important;
            font-weight: bold !important;
            text-transform: uppercase !important;
            border: 1px solid #d1d5db !important;
        }
        .dataframe td {
            border: 1px solid #d1d5db !important;
        }
        </style>
        """, unsafe_allow_html=True)

        # Tabs
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "👥 League Members",
            "📊 GW Points",
            "📅 Month Points",
            "⭐ Top Picks",
            "🏆 Rankings",
            "🏅 Awards Statistics"
        ])

        with tab1:
            st.subheader("League Members List")
            display_df = entries_df.copy()
            if max_entries:
                display_df = display_df.head(max_entries)

            # Prepare display dataframe: hide Team_ID, use Rank as index
            display_df_formatted = display_df[['Rank', 'Manager', 'Team', 'Total']].copy()
            display_df_formatted = display_df_formatted.set_index('Rank')

            st.dataframe(display_df_formatted, use_container_width=True)

            # Download button
            filename = f"fpl_{league_id}_members.csv"
            create_download_button(display_df, filename, "📥 Download CSV", key="download_members")

        with tab2:
            st.subheader("Points by Gameweek")

            # Auto-load GW Points data if not already loaded or if data was refreshed
            should_load_gw_data = ('gw_points_df' not in st.session_state) or refresh_data

            if should_load_gw_data:
                try:
                    with st.spinner("Loading gameweek points data..."):
                        gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries)

                    # Create pivot table for display with GW format
                    # Separate pivot for points and transfers
                    points_pivot = gw_points_df.pivot_table(
                        index=['Manager', 'Team'],
                        columns='GW',
                        values='Points',
                        fill_value=0
                    )

                    transfers_pivot = gw_points_df.pivot_table(
                        index=['Manager', 'Team'],
                        columns='GW',
                        values='Transfers',
                        fill_value=0
                    )

                    # Rename columns to GW1, GW2, etc.
                    points_pivot.columns = [f'GW{col}_Points' for col in points_pivot.columns]
                    transfers_pivot.columns = [f'GW{col}_Transfers' for col in transfers_pivot.columns]

                    # Combine points and transfers
                    combined_df = pd.concat([points_pivot, transfers_pivot], axis=1)

                    # Reset index to get Manager and Team as columns
                    combined_df = combined_df.reset_index()

                    # Add Total column (sum of all points columns)
                    points_cols = [f'GW{gw}_Points' for gw in sorted(gw_range)]
                    combined_df['Total'] = combined_df[points_cols].sum(axis=1)

                    # Add Rank column based on Total points (descending)
                    combined_df = combined_df.sort_values('Total', ascending=False)
                    combined_df['Rank'] = range(1, len(combined_df) + 1)

                    # Sort columns to group GW data together, with Rank, Manager, Team first and Total at the end
                    gw_cols = ['Rank', 'Manager', 'Team']
                    for gw in sorted(gw_range):
                        gw_cols.extend([f'GW{gw}_Points', f'GW{gw}_Transfers'])
                    gw_cols.append('Total')

                    # Reorder columns
                    combined_df = combined_df[gw_cols]

                    st.session_state.gw_points_df = gw_points_df
                    st.session_state.gw_display_df = combined_df

                except Exception as e:
                    st.error(f"Error loading GW data: {str(e)}")

            if 'gw_display_df' in st.session_state:
                display_df = st.session_state.gw_display_df.copy()
                # Use Rank as index
                display_df_formatted = display_df.set_index('Rank')
                st.dataframe(display_df_formatted, use_container_width=True)

                # Download button
                filename = f"fpl_{league_id}_gw_points.csv"
                flat_df = st.session_state.gw_points_df
                create_download_button(flat_df, filename, "📥 Download CSV", key="download_gw")

                # Add charts section
                st.markdown("---")
                st.subheader("📈 GW Points Analysis")

                # Chart options
                chart_col1, chart_col2 = st.columns(2)

                with chart_col1:
                    chart_type = st.selectbox(
                        "Chart Type",
                        ["Line Chart", "Bar Chart", "Box Plot"],
                        key="gw_chart_type"
                    )

                with chart_col2:
                    # Get top managers for chart
                    top_n = st.slider("Show Top N Managers", 5, 15, 10, key="gw_top_n")

                try:
                    gw_data = st.session_state.gw_points_df

                    # Calculate average points per manager (excluding 0 points - unplayed weeks)
                    gw_data_non_zero = gw_data[gw_data['Points'] > 0]
                    avg_points = gw_data_non_zero.groupby('Manager')['Points'].mean().sort_values(ascending=False)
                    top_managers = avg_points.head(top_n).index.tolist()

                    # Filter data for top managers and exclude 0 points (unplayed weeks)
                    chart_data = gw_data[gw_data['Manager'].isin(top_managers)]
                    chart_data_non_zero = chart_data[chart_data['Points'] > 0]

                    if chart_type == "Line Chart":
                        # Line chart showing points progression (excluding unplayed weeks)
                        fig = px.line(
                            chart_data_non_zero,
                            x='GW',
                            y='Points',
                            color='Manager',
                            title=f'Points Progression - Top {top_n} Managers (Excluding Unplayed Weeks)',
                            markers=True,
                            hover_data=['Team', 'Transfers']
                        )

                        fig.update_layout(
                            xaxis_title="Gameweek",
                            yaxis_title="Points",
                            legend_title="Manager",
                            height=500
                        )

                    elif chart_type == "Bar Chart":
                        # Bar chart showing average points (excluding 0 points - unplayed weeks)
                        avg_data = chart_data_non_zero.groupby('Manager').agg({
                            'Points': 'mean',
                            'Team': 'first'
                        }).reset_index()
                        avg_data = avg_data.sort_values('Points', ascending=True)

                        fig = px.bar(
                            avg_data,
                            x='Points',
                            y='Manager',
                            orientation='h',
                            title=f'Average Points per GW - Top {top_n} Managers (Excluding Unplayed Weeks)',
                            hover_data=['Team']
                        )

                        fig.update_layout(
                            xaxis_title="Average Points",
                            yaxis_title="Manager",
                            height=500
                        )

                    else:  # Box Plot
                        # Box plot showing points distribution (excluding unplayed weeks)
                        fig = px.box(
                            chart_data_non_zero,
                            x='Manager',
                            y='Points',
                            title=f'Points Distribution - Top {top_n} Managers (Excluding Unplayed Weeks)'
                        )

                        fig.update_layout(
                            xaxis_title="Manager",
                            yaxis_title="Points",
                            height=500
                        )

                        # Rotate x-axis labels for better readability
                        fig.update_xaxes(tickangle=45)

                    st.plotly_chart(fig, use_container_width=True)

                    # Summary statistics
                    st.markdown("#### 📊 Summary Statistics")
                    summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)

                    with summary_col1:
                        # Calculate league average excluding 0 points (unplayed weeks)
                        gw_data_non_zero = gw_data[gw_data['Points'] > 0]
                        avg_all = gw_data_non_zero['Points'].mean() if len(gw_data_non_zero) > 0 else 0
                        st.metric("League Average", f"{avg_all:.1f}")

                    with summary_col2:
                        highest_gw = gw_data['Points'].max()
                        st.metric("Highest GW Score", highest_gw)

                    with summary_col3:
                        lowest_gw = gw_data['Points'].min()
                        st.metric("Lowest GW Score", lowest_gw)

                    with summary_col4:
                        std_dev = gw_data['Points'].std()
                        st.metric("Standard Deviation", f"{std_dev:.1f}")

                except Exception as e:
                    st.error(f"Error creating charts: {str(e)}")

        with tab3:
            st.subheader("Points by Month")

            if 'gw_points_df' in st.session_state:
                try:
                    month_points_df = build_month_points_table_full(
                        st.session_state.gw_points_df,
                        month_mapping
                    )

                    # Prepare display dataframe: hide Team_ID, use Rank as index
                    display_cols = [col for col in month_points_df.columns if col != 'Team_ID']
                    display_df = month_points_df[display_cols].copy()
                    display_df_formatted = display_df.set_index('Rank')

                    st.dataframe(display_df_formatted, use_container_width=True)

                    # Download button
                    filename = f"fpl_{league_id}_month_points.csv"
                    create_download_button(month_points_df, filename, "📥 Download CSV", key="download_month")

                    # Chart
                    if len(month_points_df) > 0:
                        st.subheader("📈 Monthly Points Chart")

                        # Get month columns
                        month_cols = [col for col in month_points_df.columns if col.startswith('Month_') and col != 'Total']

                        if month_cols:
                            # Select top 10 entries to display
                            top_entries = month_points_df.nlargest(10, 'Total')

                            # Melt data for plotly
                            plot_data = top_entries.melt(
                                id_vars=['Manager'],
                                value_vars=month_cols,
                                var_name='Month',
                                value_name='Points'
                            )

                            fig = px.line(
                                plot_data,
                                x='Month',
                                y='Points',
                                color='Manager',
                                title='Monthly Points (Top 10)',
                                markers=True
                            )

                            fig.update_layout(
                                xaxis_title="Month",
                                yaxis_title="Points",
                                legend_title="Manager"
                            )

                            st.plotly_chart(fig, use_container_width=True)

                    # Add charts section
                    st.markdown("---")
                    st.subheader("📈 Month Points Analysis")

                    # Chart options
                    chart_col1, chart_col2 = st.columns(2)

                    with chart_col1:
                        chart_type = st.selectbox(
                            "Chart Type",
                            ["Line Chart", "Bar Chart", "Box Plot"],
                            key="month_chart_type"
                        )

                    with chart_col2:
                        # Get top managers for chart
                        top_n = st.slider("Show Top N Managers", 5, 15, 10, key="month_top_n")

                    # Prepare data for analysis
                    if len(month_points_df) > 0:
                        # Create month data for analysis (melt the dataframe)
                        month_cols = [col for col in month_points_df.columns if col.startswith('Month_')]

                        if month_cols:
                            try:
                                # Melt data for analysis
                                month_analysis_data = month_points_df.melt(
                                    id_vars=['Manager', 'Team'],
                                    value_vars=month_cols,
                                    var_name='Month',
                                    value_name='Points'
                                )

                                # Calculate average points per manager
                                avg_points = month_analysis_data.groupby('Manager')['Points'].mean().sort_values(ascending=False)
                                top_managers = avg_points.head(top_n).index.tolist()

                                # Filter data for top managers
                                chart_data = month_analysis_data[month_analysis_data['Manager'].isin(top_managers)]

                                if chart_type == "Line Chart":
                                    # Line chart showing monthly points progression
                                    fig = px.line(
                                        chart_data,
                                        x='Month',
                                        y='Points',
                                        color='Manager',
                                        title=f'Monthly Points Progression - Top {top_n} Managers',
                                        markers=True,
                                        hover_data=['Team']
                                    )

                                    fig.update_layout(
                                        xaxis_title="Month",
                                        yaxis_title="Points",
                                        legend_title="Manager",
                                        height=500
                                    )

                                elif chart_type == "Bar Chart":
                                    # Bar chart showing average points per month
                                    avg_data = chart_data.groupby('Manager').agg({
                                        'Points': 'mean',
                                        'Team': 'first'
                                    }).reset_index()
                                    avg_data = avg_data.sort_values('Points', ascending=True)

                                    fig = px.bar(
                                        avg_data,
                                        x='Points',
                                        y='Manager',
                                        orientation='h',
                                        title=f'Average Points per Month - Top {top_n} Managers',
                                        hover_data=['Team']
                                    )

                                    fig.update_layout(
                                        xaxis_title="Average Points",
                                        yaxis_title="Manager",
                                        height=500
                                    )

                                else:  # Box Plot
                                    # Box plot showing monthly points distribution
                                    fig = px.box(
                                        chart_data,
                                        x='Manager',
                                        y='Points',
                                        title=f'Monthly Points Distribution - Top {top_n} Managers'
                                    )

                                    fig.update_layout(
                                        xaxis_title="Manager",
                                        yaxis_title="Points",
                                        height=500
                                    )

                                    # Rotate x-axis labels for better readability
                                    fig.update_xaxes(tickangle=45)

                                st.plotly_chart(fig, use_container_width=True)

                                # Summary statistics
                                st.markdown("#### 📊 Summary Statistics")
                                summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)

                                with summary_col1:
                                    # Calculate league average for monthly points
                                    avg_all = month_analysis_data['Points'].mean()
                                    st.metric("League Average", f"{avg_all:.1f}")

                                with summary_col2:
                                    highest_month = month_analysis_data['Points'].max()
                                    st.metric("Highest Month Score", highest_month)

                                with summary_col3:
                                    lowest_month = month_analysis_data['Points'].min()
                                    st.metric("Lowest Month Score", lowest_month)

                                with summary_col4:
                                    std_dev = month_analysis_data['Points'].std()
                                    st.metric("Standard Deviation", f"{std_dev:.1f}")

                            except Exception as e:
                                st.error(f"Error creating month analysis charts: {str(e)}")

                except Exception as e:
                    st.error(f"Error calculating monthly points: {str(e)}")
            else:
                st.info("GW Points data is loading...")

        with tab4:
            st.subheader("Top 5 Most Picked Players")

            # Options for top picks
            col1, col2 = st.columns(2)
            with col1:
                single_gw = st.checkbox("Single GW only", value=False)
            with col2:
                if single_gw:
                    selected_gw = st.selectbox("Select GW", gw_range)
                    analysis_gw_range = [selected_gw]
                else:
                    analysis_gw_range = gw_range

            if st.button("🔄 Calculate Top Picks", key="load_picks"):
                try:
                    with st.spinner("Calculating top picks..."):
                        top_picks_df = compute_top_picks(
                            entries_df,
                            analysis_gw_range,
                            bootstrap_df,
                            max_entries
                        )

                    st.session_state.top_picks_df = top_picks_df

                except Exception as e:
                    st.error(f"Error calculating top picks: {str(e)}")

            if 'top_picks_df' in st.session_state:
                top_picks_df = st.session_state.top_picks_df

                if not top_picks_df.empty:
                    st.dataframe(top_picks_df, use_container_width=True)

                    # Download button
                    filename = f"fpl_{league_id}_top_picks.csv"
                    create_download_button(top_picks_df, filename, "📥 Download CSV", key="download_picks")

                    # Chart
                    st.subheader("📊 Top Picks Chart")
                    fig = px.bar(
                        top_picks_df,
                        x='Player',
                        y='Times_Picked',
                        title='Top 5 Most Picked Players',
                        text='Percent_Of_Entries'
                    )

                    fig.update_traces(texttemplate='%{text}%', textposition='outside')
                    fig.update_layout(
                        xaxis_title="Player",
                        yaxis_title="Times Picked",
                        showlegend=False
                    )

                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No picks data available")

        with tab5:
            st.subheader("🏆 League Rankings")

            # Get current GW and month for defaults
            if 'current_gw' not in st.session_state:
                st.session_state.current_gw = get_current_gw()

            current_month = get_current_month(st.session_state.current_gw, month_mapping)

            # Create two columns for the ranking tables
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### 📅 Weekly Rankings")

                # GW selector
                selected_gw = st.selectbox(
                    "Select Gameweek",
                    options=gw_range,
                    index=gw_range.index(st.session_state.current_gw) if st.session_state.current_gw in gw_range else 0,
                    key="rank_gw_selector"
                )

                if 'gw_points_df' in st.session_state:
                    try:
                        weekly_ranking = build_weekly_ranking(st.session_state.gw_points_df, selected_gw)

                        if not weekly_ranking.empty:
                            # Custom styling for the ranking table
                            st.markdown("""
                            <style>
                            .ranking-table {
                                border-radius: 10px;
                                overflow: hidden;
                                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                            }
                            .ranking-table .dataframe {
                                border: none;
                            }
                            .ranking-table .dataframe th {
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                color: white;
                                font-weight: bold;
                                text-align: center;
                                padding: 12px;
                            }
                            .ranking-table .dataframe td {
                                text-align: center;
                                padding: 10px;
                                border-bottom: 1px solid #e0e0e0;
                            }
                            .ranking-table .dataframe tr:nth-child(even) {
                                background-color: #f8f9fa;
                            }
                            .ranking-table .dataframe tr:hover {
                                background-color: #e3f2fd;
                            }
                            </style>
                            """, unsafe_allow_html=True)

                            # Display the table with custom styling
                            st.markdown('<div class="ranking-table">', unsafe_allow_html=True)
                            st.dataframe(
                                weekly_ranking,
                                use_container_width=True,
                                hide_index=True
                            )
                            st.markdown('</div>', unsafe_allow_html=True)

                            # Highlight top 3
                            if len(weekly_ranking) >= 3:
                                st.markdown("#### 🎖️ Top 3 This Week")
                                top3 = weekly_ranking.head(3)

                                for _, row in top3.iterrows():
                                    medal = row['Medal']
                                    rank = row['Rank']
                                    manager = row['Manager']
                                    team = row['Team']
                                    points = row['Points']
                                    transfers = row['Transfers']

                                    display_text = f"{medal} **{manager}** ({team}) - {points} points, {transfers} transfers"

                                    if rank == 1:
                                        st.success(display_text)
                                    elif rank == 2:
                                        st.info(display_text)
                                    elif rank == 3:
                                        st.warning(display_text)

                            # Download button
                            filename = f"fpl_{league_id}_weekly_ranking_gw{selected_gw}.csv"
                            create_download_button(weekly_ranking, filename, "📥 Download Weekly Ranking", key="download_weekly_rank")
                        else:
                            st.info(f"No data available for GW {selected_gw}")
                    except Exception as e:
                        st.error(f"Error creating weekly ranking: {str(e)}")
                else:
                    st.info("GW Points data is loading...")

            with col2:
                st.markdown("### 📊 Monthly Rankings")

                # Get available months from month mapping
                available_months = sorted(set(month_mapping.values()))
                current_month = get_current_month(st.session_state.current_gw, month_mapping)

                # Month selector
                selected_month = st.selectbox(
                    "Select Month",
                    options=available_months,
                    index=available_months.index(current_month) if current_month in available_months else 0,
                    key="rank_month_selector"
                )

                if 'gw_points_df' in st.session_state:
                    try:
                        monthly_ranking = build_monthly_ranking_full(
                            st.session_state.gw_points_df,
                            month_mapping,
                            selected_month
                        )

                        if not monthly_ranking.empty:
                            # Display the table with custom styling
                            st.markdown('<div class="ranking-table">', unsafe_allow_html=True)
                            st.dataframe(
                                monthly_ranking,
                                use_container_width=True,
                                hide_index=True
                            )
                            st.markdown('</div>', unsafe_allow_html=True)

                            # Highlight top 3
                            if len(monthly_ranking) >= 3:
                                st.markdown("#### 🏅 Top 3 This Month")
                                top3 = monthly_ranking.head(3)

                                for _, row in top3.iterrows():
                                    medal = row['Medal']
                                    rank = row['Rank']
                                    manager = row['Manager']
                                    team = row['Team']
                                    points = row['Points']
                                    transfers = row['Transfers']

                                    display_text = f"{medal} **{manager}** ({team}) - {points} points, {transfers} transfers"

                                    if rank == 1:
                                        st.success(display_text)
                                    elif rank == 2:
                                        st.info(display_text)
                                    elif rank == 3:
                                        st.warning(display_text)

                            # Download button
                            filename = f"fpl_{league_id}_monthly_ranking_month{selected_month}.csv"
                            create_download_button(monthly_ranking, filename, "📥 Download Monthly Ranking", key="download_monthly_rank")
                        else:
                            st.info(f"No data available for Month {selected_month}")
                    except Exception as e:
                        st.error(f"Error creating monthly ranking: {str(e)}")
                else:
                    st.info("GW Points data is loading...")

            # Overall statistics section
            if 'gw_points_df' in st.session_state:
                st.markdown("---")
                st.markdown("### 📈 Overall Statistics")

                col1, col2, col3, col4 = st.columns(4)

                try:
                    gw_data = st.session_state.gw_points_df

                    with col1:
                        total_entries = len(gw_data['Team_ID'].unique())
                        st.metric("Total Teams", total_entries)

                    with col2:
                        # Calculate average excluding 0 points (unplayed weeks)
                        gw_data_non_zero = gw_data[gw_data['Points'] > 0]
                        avg_points = gw_data_non_zero['Points'].mean() if len(gw_data_non_zero) > 0 else 0
                        st.metric("Average Points/GW", f"{avg_points:.1f}")

                    with col3:
                        highest_gw_score = gw_data['Points'].max()
                        st.metric("Highest GW Score", highest_gw_score)

                    with col4:
                        total_transfers = gw_data['Transfers'].sum()
                        st.metric("Total Transfers", total_transfers)

                    # Performance chart
                    st.markdown("#### 📊 Performance Distribution")

                    # Create histogram of points distribution (excluding unplayed weeks)
                    gw_data_non_zero = gw_data[gw_data['Points'] > 0]

                    fig = go.Figure()
                    fig.add_trace(go.Histogram(
                        x=gw_data_non_zero['Points'],
                        nbinsx=20,
                        name='Points Distribution',
                        marker_color='rgba(55, 128, 191, 0.7)',
                        marker_line=dict(color='rgba(55, 128, 191, 1.0)', width=1)
                    ))

                    fig.update_layout(
                        title='Points Distribution Across All Gameweeks (Excluding Unplayed Weeks)',
                        xaxis_title='Points',
                        yaxis_title='Frequency',
                        showlegend=False,
                        height=400
                    )

                    st.plotly_chart(fig, use_container_width=True)

                except Exception as e:
                    st.error(f"Error creating statistics: {str(e)}")

        with tab6:
            st.subheader("🏅 Awards Statistics")
            st.markdown("Track the most successful managers by weekly and monthly wins")

            if 'gw_points_df' in st.session_state:
                try:
                    # Calculate awards statistics
                    with st.spinner("Calculating awards statistics..."):
                        awards_df = calculate_awards_statistics(
                            st.session_state.gw_points_df,
                            month_mapping
                        )

                    if not awards_df.empty:
                        # Display awards table
                        st.markdown("### 🏆 Awards Leaderboard")

                        # Custom styling for awards table
                        st.markdown("""
                        <style>
                        .awards-table {
                            border-radius: 10px;
                            overflow: hidden;
                            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                        }
                        .awards-table .dataframe th {
                            background: linear-gradient(135deg, #ffd700 0%, #ffb347 100%);
                            color: #333;
                            font-weight: bold;
                            text-align: center;
                            padding: 12px;
                        }
                        .awards-table .dataframe td {
                            text-align: center;
                            padding: 10px;
                            border-bottom: 1px solid #e0e0e0;
                        }
                        .awards-table .dataframe tr:nth-child(even) {
                            background-color: #fffbf0;
                        }
                        .awards-table .dataframe tr:hover {
                            background-color: #fff3cd;
                        }
                        </style>
                        """, unsafe_allow_html=True)

                        # Display the table
                        st.markdown('<div class="awards-table">', unsafe_allow_html=True)
                        st.dataframe(awards_df, use_container_width=True, hide_index=True)
                        st.markdown('</div>', unsafe_allow_html=True)

                        # Highlight top 3 award winners
                        if len(awards_df) >= 3:
                            st.markdown("#### 🎖️ Top 3 Award Winners")
                            top3_awards = awards_df.head(3)

                            for _, row in top3_awards.iterrows():
                                medal = row['Medal']
                                rank = row['Rank']
                                manager = row['Manager']
                                team = row['Team']
                                weekly_wins = row['Weekly_Wins']
                                monthly_wins = row['Monthly_Wins']
                                total_awards = row['Total_Awards']

                                display_text = f"{medal} **{manager}** ({team}) - {total_awards} total awards ({weekly_wins} weekly, {monthly_wins} monthly)"

                                if rank == 1:
                                    st.success(display_text)
                                elif rank == 2:
                                    st.info(display_text)
                                elif rank == 3:
                                    st.warning(display_text)

                        # Awards visualization
                        st.markdown("---")
                        st.markdown("### 📊 Awards Visualization")

                        # Chart selection
                        viz_col1, viz_col2 = st.columns(2)

                        with viz_col1:
                            chart_option = st.selectbox(
                                "Chart Type",
                                ["Stacked Bar Chart", "Pie Chart", "Scatter Plot"],
                                key="awards_chart_type"
                            )

                        with viz_col2:
                            show_top_n = st.slider("Show Top N Managers", 5, 20, 10, key="awards_top_n")

                        # Filter data for visualization
                        viz_data = awards_df.head(show_top_n)

                        if chart_option == "Stacked Bar Chart":
                            # Stacked bar chart showing weekly vs monthly wins
                            fig = go.Figure()

                            fig.add_trace(go.Bar(
                                name='Weekly Wins',
                                x=viz_data['Manager'],
                                y=viz_data['Weekly_Wins'],
                                marker_color='lightblue'
                            ))

                            fig.add_trace(go.Bar(
                                name='Monthly Wins',
                                x=viz_data['Manager'],
                                y=viz_data['Monthly_Wins'],
                                marker_color='gold'
                            ))

                            fig.update_layout(
                                title=f'Awards Breakdown - Top {show_top_n} Managers',
                                xaxis_title='Manager',
                                yaxis_title='Number of Awards',
                                barmode='stack',
                                height=500
                            )

                            fig.update_xaxes(tickangle=45)

                        elif chart_option == "Pie Chart":
                            # Pie chart showing total awards distribution
                            fig = px.pie(
                                viz_data,
                                values='Total_Awards',
                                names='Manager',
                                title=f'Total Awards Distribution - Top {show_top_n} Managers'
                            )

                            fig.update_layout(height=500)

                        else:  # Scatter Plot
                            # Scatter plot: Weekly vs Monthly wins
                            fig = px.scatter(
                                viz_data,
                                x='Weekly_Wins',
                                y='Monthly_Wins',
                                size='Total_Awards',
                                hover_name='Manager',
                                hover_data=['Team'],
                                title=f'Weekly vs Monthly Wins - Top {show_top_n} Managers',
                                labels={'Weekly_Wins': 'Weekly Wins', 'Monthly_Wins': 'Monthly Wins'}
                            )

                            fig.update_layout(height=500)

                        st.plotly_chart(fig, use_container_width=True)

                        # Awards summary metrics
                        st.markdown("#### 📈 Awards Summary")
                        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

                        with metric_col1:
                            total_weekly_awards = awards_df['Weekly_Wins'].sum()
                            st.metric("Total Weekly Awards", total_weekly_awards)

                        with metric_col2:
                            total_monthly_awards = awards_df['Monthly_Wins'].sum()
                            st.metric("Total Monthly Awards", total_monthly_awards)

                        with metric_col3:
                            managers_with_awards = len(awards_df[awards_df['Total_Awards'] > 0])
                            st.metric("Managers with Awards", managers_with_awards)

                        with metric_col4:
                            max_awards = awards_df['Total_Awards'].max()
                            st.metric("Most Awards (Single Manager)", max_awards)

                        # Download button
                        filename = f"fpl_{league_id}_awards_statistics.csv"
                        create_download_button(awards_df, filename, "📥 Download Awards Statistics", key="download_awards")

                    else:
                        st.info("No awards data available")

                except Exception as e:
                    st.error(f"Error calculating awards statistics: {str(e)}")
            else:
                st.info("GW Points data is loading...")

    else:
        st.info("👆 Please configure settings in the sidebar")

if __name__ == "__main__":
    main()