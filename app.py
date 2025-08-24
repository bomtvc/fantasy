import streamlit as st
import pandas as pd
import requests
import time
import base64
import os
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

def get_chip_icon_base64(icon_path: str) -> str:
    """
    Convert chip icon to base64 for embedding in HTML
    """
    try:
        if os.path.exists(icon_path):
            with open(icon_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
                return f"data:image/png;base64,{encoded_string}"
        else:
            # Return a default icon if file not found
            return ""
    except Exception:
        return ""

def show_temporary_message(message: str, message_type: str = "success"):
    """
    Show a temporary message - simplified version that just shows the message
    For Streamlit, we'll rely on the natural flow to clear messages
    """
    if message_type == "success":
        # Suppress success messages to reduce UI clutter
        pass
    elif message_type == "warning":
        # Only show critical warnings, suppress routine ones
        if "404 Client Error" not in message and "Unable to fetch data for entry" not in message:
            st.warning(message)
    elif message_type == "error":
        st.error(message)
    elif message_type == "info":
        # Suppress info messages to reduce UI clutter
        pass

def render_awards_summary_table(df: pd.DataFrame, month_mapping: Dict[int, int]) -> str:
    """
    Render awards summary table with merged cells for monthly winners
    """
    if df.empty:
        return "<p>No data available</p>"

    # Group GWs by month for merging cells
    month_groups = {}
    for _, row in df.iterrows():
        gw = row['GW']
        month = month_mapping.get(gw, 1)
        if month not in month_groups:
            month_groups[month] = []
        month_groups[month].append(row)

    # Start building HTML
    html = '<div class="table-container">'
    html += '<table class="custom-table awards-summary-table">'

    # Header
    html += '<thead><tr>'
    html += '<th>GW</th>'
    html += '<th>Weekly Wins</th>'
    html += '<th>Monthly Wins</th>'
    html += '</tr></thead>'

    # Body
    html += '<tbody>'

    for month in sorted(month_groups.keys()):
        month_rows = month_groups[month]
        month_winner = month_rows[0]['Monthly_Wins'] if month_rows else ""

        for i, row in enumerate(month_rows):
            html += '<tr>'

            # GW column
            html += f'<td class="gw-cell">{row["GW"]}</td>'

            # Weekly Wins column
            weekly_winner = row['Weekly_Wins']
            html += f'<td class="manager-cell">{weekly_winner}</td>'

            # Monthly Wins column (merged for the month)
            if i == 0:  # First row of the month
                rowspan = len(month_rows)
                html += f'<td class="monthly-winner-cell" rowspan="{rowspan}">{month_winner}</td>'
            # Other rows don't add the monthly cell (it's merged)

            html += '</tr>'

    html += '</tbody></table></div>'
    return html

def render_custom_table(df: pd.DataFrame, table_type: str = "default", team_id_mapping: dict = None) -> str:
    """
    Render a DataFrame as a custom HTML table with CSS styling
    For GW Points table, creates hyperlinks to team lineups
    """
    if df.empty:
        return "<p>No data available</p>"

    # Start building HTML
    html = '<div class="table-container">'
    html += '<table class="custom-table">'

    # Header
    html += '<thead><tr>'
    for col in df.columns:
        html += f'<th>{col}</th>'
    html += '</tr></thead>'

    # Body
    html += '<tbody>'
    for _, row in df.iterrows():
        html += '<tr>'

        # Get Team_ID for this row if available (for GW Points hyperlinks)
        team_id = None
        if team_id_mapping and 'Manager' in row:
            team_id = team_id_mapping.get(row['Manager'])

        for i, (col, value) in enumerate(row.items()):
            # Apply different CSS classes based on column type
            css_class = ""

            if col == 'Rank' or (i == 0 and table_type in ['gw', 'month', 'league']):
                rank_value = int(value) if pd.notna(value) else 0
                if rank_value == 1:
                    css_class = "rank-cell rank-1"
                elif rank_value == 2:
                    css_class = "rank-cell rank-2"
                elif rank_value == 3:
                    css_class = "rank-cell rank-3"
                else:
                    css_class = "rank-cell"
            elif col == 'Manager':
                css_class = "manager-cell"
            elif col == 'Team':
                css_class = "team-cell"
            elif col == 'Total':
                css_class = "total-cell"
            elif 'Points' in col:
                css_class = "points-cell"
            elif 'Transfers' in col:
                css_class = "transfers-cell"
            elif table_type == "chip" and col.startswith('GW'):
                css_class = "chip-cell"
            elif table_type == "transfer" and col.startswith('GW'):
                css_class = "transfer-cell"
            elif table_type == "fun_stats":
                if col == 'GW':
                    css_class = "gw-cell"
                elif 'Captain' in col:
                    css_class = "captain-cell"
                elif 'Bench' in col:
                    css_class = "bench-cell"
                elif 'Transfer' in col:
                    css_class = "transfer-cell"

            # Format value and create hyperlink for GW Points
            if pd.isna(value):
                display_value = "-"
            elif isinstance(value, (int, float)):
                if col == 'Transfers' or 'Transfers' in col:
                    display_value = f"{int(value)}" if value != 0 else "-"
                else:
                    formatted_value = f"{int(value)}" if value == int(value) else f"{value:.1f}"

                    # Create hyperlink for GW Points columns
                    if (table_type == "gw" and 'Points' in col and 'GW' in col and
                        team_id and value > 0):
                        # Extract GW number from column name (e.g., "GW1_Points" -> "1")
                        gw_num = col.replace('GW', '').replace('_Points', '')
                        lineup_url = f"https://fantasy.premierleague.com/entry/{team_id}/event/{gw_num}"
                        display_value = f'<a href="{lineup_url}" target="_blank" class="gw-points-link">{formatted_value}</a>'
                    else:
                        display_value = formatted_value
            else:
                # Handle transfer display with colors
                if table_type == "transfer" and col.startswith('GW') and str(value) != '-':
                    transfer_text = str(value)

                    # Handle multiple transfers separated by ' | '
                    if ' | ' in transfer_text:
                        transfers = transfer_text.split(' | ')
                        formatted_transfers = []
                        for transfer in transfers:
                            if ' - ' in transfer:
                                # Parse player_in (points) - player_out (points) format
                                parts = transfer.split(' - ', 1)
                                player_in_part = parts[0]
                                player_out_part = parts[1]

                                formatted_transfer = f'<span style="color: #4caf50; font-weight: bold;">{player_in_part}</span> - <span style="color: #f44336; font-weight: bold;">{player_out_part}</span>'
                                formatted_transfers.append(formatted_transfer)
                            else:
                                formatted_transfers.append(transfer)
                        display_value = '<br>'.join(formatted_transfers)
                    elif ' - ' in transfer_text:
                        # Parse player_in (points) - player_out (points) format
                        parts = transfer_text.split(' - ', 1)
                        player_in_part = parts[0]
                        player_out_part = parts[1]

                        display_value = f'<span style="color: #4caf50; font-weight: bold;">{player_in_part}</span> - <span style="color: #f44336; font-weight: bold;">{player_out_part}</span>'
                    else:
                        display_value = transfer_text
                # Handle chip display with icons and colors
                elif table_type == "chip" and col.startswith('GW') and str(value) != '-':
                    chip_name = str(value)
                    chip_configs = {
                        'wildcard': {
                            'icon': 'statics/wildcard.png',
                            'text': 'Wildcard',
                            'color': '#ff9800'
                        },
                        'freehit': {
                            'icon': 'statics/freehit.png',
                            'text': 'Free Hit',
                            'color': '#2196f3'
                        },
                        'bboost': {
                            'icon': 'statics/bboost.png',
                            'text': 'Bench Boost',
                            'color': '#4caf50'
                        },
                        'triple_captain': {
                            'icon': 'statics/3xc.png',
                            'text': 'Triple Captain',
                            'color': '#9c27b0'
                        },
                        '3xc': {
                            'icon': 'statics/3xc.png',
                            'text': 'Triple Captain',
                            'color': '#9c27b0'
                        }
                    }

                    chip_config = chip_configs.get(chip_name.lower())
                    if chip_config:
                        icon_base64 = get_chip_icon_base64(chip_config['icon'])
                        if icon_base64:
                            display_value = f'''
                            <div class="chip-container" style="
                                display: flex;
                                flex-direction: column;
                                align-items: center;
                                padding: 8px 4px;
                                border-radius: 8px;
                                background-color: {chip_config['color']};
                                color: white;
                                min-width: 60px;
                                font-size: 10px;
                                font-weight: bold;
                                text-align: center;
                                line-height: 1.2;
                            ">
                                <img src="{icon_base64}" alt="{chip_config['text']}" style="
                                    width: 24px;
                                    height: 24px;
                                    margin-bottom: 4px;
                                    filter: brightness(0) invert(1);
                                ">
                                <span>{chip_config['text']}</span>
                            </div>
                            '''
                        else:
                            # Fallback to text only if icon not found
                            display_value = f'<span style="padding: 4px 8px; border-radius: 8px; background-color: {chip_config["color"]}; color: white; font-size: 11px; font-weight: bold;">{chip_config["text"]}</span>'
                    else:
                        display_value = f'<span style="padding: 4px 8px; border-radius: 8px; background-color: #607d8b; color: white; font-size: 11px; font-weight: bold;">🎲 {chip_name.upper()}</span>'
                # Handle fun stats transfer display with HTML colors
                elif table_type == "fun_stats" and 'Transfer' in col and str(value) != '-':
                    # Value already contains HTML formatting from the function
                    display_value = str(value)
                else:
                    display_value = str(value)

            html += f'<td class="{css_class}">{display_value}</td>'
        html += '</tr>'

    html += '</tbody></table></div>'
    return html

def clear_all_cache():
    """
    Clear all cached data and session state
    """
    # Clear Streamlit cache
    st.cache_data.clear()

    # Clear session state data
    cache_keys = ['entries_df', 'bootstrap_df', 'gw_range', 'gw_points_df', 'gw_display_df', 'top_picks_df', 'fun_stats_df', 'data_loaded_at']
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
    # status_placeholder = st.empty()
    # status_placeholder.success(f"Loaded {len(all_entries)} entries from {page-1} pages")
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

@st.cache_data(ttl=config.API_CACHE_TTL)
def get_entry_transfers(entry_id: int) -> Optional[Dict]:
    """
    Get transfer history for a specific entry
    """
    try:
        url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/transfers/"
        data = fetch_json(url)
        return data
    except Exception as e:
        show_temporary_message(f"Unable to fetch transfer data for entry {entry_id}: {str(e)}", "warning")
        return None

def get_player_gw_points(element_id: int, gw: int) -> int:
    """
    Get player points for a specific gameweek from element-summary API
    """
    try:
        url = f"https://fantasy.premierleague.com/api/element-summary/{element_id}/"
        data = fetch_json(url)

        # Find the specific gameweek in history
        for event in data.get('history', []):
            if event.get('round') == gw:
                return event.get('total_points', 0)

        return 0
    except Exception as e:
        return 0

def build_transfer_history_table(entries_df: pd.DataFrame, bootstrap_df: pd.DataFrame, max_entries: Optional[int] = None) -> pd.DataFrame:
    """
    Build transfer history table for all entries showing transfers by gameweek
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)

    results = []
    total_requests = len(entries_df)

    # Progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Create player name mapping
    player_mapping = dict(zip(bootstrap_df['id'], bootstrap_df['web_name']))

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_info = {}
        for _, entry in entries_df.iterrows():
            future = executor.submit(get_entry_transfers, entry['Team_ID'])
            future_to_info[future] = (entry['Team_ID'], entry['Manager'], entry['Team'])

        # Collect results
        completed = 0
        for future in as_completed(future_to_info):
            team_id, manager, team = future_to_info[future]
            completed += 1

            # Update progress
            progress = completed / total_requests
            progress_bar.progress(progress)
            status_text.text(f"Fetching transfer data: {completed}/{total_requests} ({progress:.1%})")

            try:
                data = future.result()
                if data and isinstance(data, list):
                    for transfer in data:
                        element_in = transfer.get('element_in')
                        element_out = transfer.get('element_out')
                        event = transfer.get('event')

                        # Get player names
                        player_in_name = player_mapping.get(element_in, f"Player_{element_in}") if element_in else "Unknown"
                        player_out_name = player_mapping.get(element_out, f"Player_{element_out}") if element_out else "Unknown"

                        # Get player points for the transfer GW
                        player_in_points = get_player_gw_points(element_in, event) if element_in and event else 0
                        player_out_points = get_player_gw_points(element_out, event) if element_out and event else 0

                        # Create transfer string with points
                        transfer_text = f"{player_in_name} ({player_in_points}) - {player_out_name} ({player_out_points})"

                        results.append({
                            'Team_ID': team_id,
                            'Manager': manager,
                            'Team': team,
                            'GW': event,
                            'Transfer': transfer_text,
                            'Player_In': player_in_name,
                            'Player_Out': player_out_name,
                            'Player_In_Points': player_in_points,
                            'Player_Out_Points': player_out_points
                        })
                else:
                    # Add empty entry if no transfers
                    pass

            except Exception as e:
                show_temporary_message(f"Error processing transfers for entry {team_id}: {str(e)}", "warning")

            # Small delay to avoid rate limit
            time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)

    progress_bar.empty()
    status_text.empty()

    if not results:
        # Return empty dataframe with proper columns if no transfers found
        return pd.DataFrame(columns=['Team_ID', 'Manager', 'Team', 'GW', 'Transfer', 'Player_In', 'Player_Out', 'Player_In_Points', 'Player_Out_Points'])

    return pd.DataFrame(results)

def build_chip_history_table(entries_df: pd.DataFrame, gw_range: List[int], max_entries: Optional[int] = None) -> pd.DataFrame:
    """
    Build chip history table for all entries showing which chips were used in each GW
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
            status_text.text(f"Fetching chip data: {completed}/{total_requests} ({progress:.1%})")

            try:
                data = future.result()
                active_chip = None
                if data:
                    active_chip = data.get('active_chip')

                results.append({
                    'Team_ID': team_id,
                    'Manager': manager,
                    'Team': team,
                    'GW': gw,
                    'Active_Chip': active_chip if active_chip else '-'
                })
            except Exception as e:
                show_temporary_message(f"Error processing entry {team_id}, GW {gw}: {str(e)}", "warning")
                results.append({
                    'Team_ID': team_id,
                    'Manager': manager,
                    'Team': team,
                    'GW': gw,
                    'Active_Chip': '-'
                })

            # Small delay to avoid rate limit
            time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)

    progress_bar.empty()
    status_text.empty()

    if not results:
        raise FPLError("Unable to fetch chip data for any entry")

    return pd.DataFrame(results)

def build_fun_stats_table(entries_df: pd.DataFrame, gw_range: List[int], bootstrap_df: pd.DataFrame,
                         max_entries: Optional[int] = None) -> pd.DataFrame:
    """
    Build fun statistics table showing best/worst captains, best bench, and best/worst transfers for each GW
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)

    results = []

    # Only process GWs that have finished (have results)
    completed_gws = [gw for gw in gw_range if gw <= max(gw_range)]

    total_requests = len(entries_df) * len(completed_gws)

    # Progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()

    # Create player name mapping
    player_mapping = dict(zip(bootstrap_df['id'], bootstrap_df['web_name']))

    for gw in completed_gws:
        status_text.text(f"Processing GW {gw}...")

        gw_data = []
        completed = 0

        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
            # Submit all tasks for this GW
            future_to_info = {}
            for _, entry in entries_df.iterrows():
                future = executor.submit(get_entry_gw_picks, entry['Team_ID'], gw)
                future_to_info[future] = (entry['Team_ID'], entry['Manager'], entry['Team'])

            # Collect results for this GW
            for future in as_completed(future_to_info):
                team_id, manager, team = future_to_info[future]
                completed += 1

                # Update progress
                progress = (completed + (gw - 1) * len(entries_df)) / total_requests
                progress_bar.progress(progress)

                try:
                    data = future.result()
                    if data and 'picks' in data:
                        picks = data['picks']

                        # Find captain
                        captain_pick = next((p for p in picks if p.get('is_captain')), None)
                        captain_element = captain_pick.get('element') if captain_pick else None
                        captain_points = 0
                        captain_name = "Unknown"

                        if captain_element:
                            captain_points = get_player_gw_points(captain_element, gw)
                            captain_name = player_mapping.get(captain_element, f"Player_{captain_element}")
                            # Captain points are doubled
                            captain_points *= captain_pick.get('multiplier', 1)

                        # Find bench players (positions 12, 13, 14, 15)
                        bench_picks = [p for p in picks if p.get('position', 0) in [12, 13, 14, 15]]
                        bench_total_points = 0

                        for bench_pick in bench_picks:
                            element_id = bench_pick.get('element')
                            if element_id:
                                player_points = get_player_gw_points(element_id, gw)
                                bench_total_points += player_points

                        # Get transfer data for this GW
                        transfer_diff = None  # None means no transfers made
                        try:
                            transfer_data = get_entry_transfers(team_id)
                            if transfer_data and isinstance(transfer_data, list):
                                gw_transfers = [t for t in transfer_data if t.get('event') == gw]

                                if gw_transfers:  # Only calculate if there are transfers
                                    total_in_points = 0
                                    total_out_points = 0

                                    for transfer in gw_transfers:
                                        element_in = transfer.get('element_in')
                                        element_out = transfer.get('element_out')

                                        if element_in:
                                            in_points = get_player_gw_points(element_in, gw)
                                            total_in_points += in_points

                                        if element_out:
                                            out_points = get_player_gw_points(element_out, gw)
                                            total_out_points += out_points

                                    transfer_diff = total_in_points - total_out_points
                        except:
                            transfer_diff = None

                        gw_data.append({
                            'team_id': team_id,
                            'manager': manager,
                            'team': team,
                            'captain_element': captain_element,
                            'captain_name': captain_name,
                            'captain_points': captain_points,
                            'bench_total_points': bench_total_points,
                            'transfer_diff': transfer_diff
                        })

                except Exception:
                    # Add empty data for failed requests
                    gw_data.append({
                        'team_id': team_id,
                        'manager': manager,
                        'team': team,
                        'captain_element': None,
                        'captain_name': "Unknown",
                        'captain_points': 0,
                        'bench_total_points': 0,
                        'transfer_diff': None  # No transfers for failed requests
                    })

                # Small delay to avoid rate limit
                time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)

        # Process GW results
        if gw_data:
            # Find best and worst captains (handle ties)
            max_captain_points = max(gw_data, key=lambda x: x['captain_points'])['captain_points']
            min_captain_points = min(gw_data, key=lambda x: x['captain_points'])['captain_points']
            max_bench_points = max(gw_data, key=lambda x: x['bench_total_points'])['bench_total_points']

            # Find best and worst transfers (only for managers who made transfers)
            transfer_data = [x for x in gw_data if x['transfer_diff'] is not None]

            if transfer_data:  # Only calculate if there are transfers
                max_transfer_diff = max(transfer_data, key=lambda x: x['transfer_diff'])['transfer_diff']
                min_transfer_diff = min(transfer_data, key=lambda x: x['transfer_diff'])['transfer_diff']
            else:
                max_transfer_diff = None
                min_transfer_diff = None

            # Get all managers with max/min scores
            best_captains = [x for x in gw_data if x['captain_points'] == max_captain_points]
            worst_captains = [x for x in gw_data if x['captain_points'] == min_captain_points]
            best_benches = [x for x in gw_data if x['bench_total_points'] == max_bench_points]

            # Get best/worst transfers only from managers who made transfers
            if transfer_data and max_transfer_diff is not None and min_transfer_diff is not None:
                best_transfers = [x for x in transfer_data if x['transfer_diff'] == max_transfer_diff]
                worst_transfers = [x for x in transfer_data if x['transfer_diff'] == min_transfer_diff]
            else:
                best_transfers = []
                worst_transfers = []

            # Format display strings
            best_captain_str = " | ".join([f"{x['manager']} - {x['captain_name']} ({x['captain_points']})" for x in best_captains])
            worst_captain_str = " | ".join([f"{x['manager']} - {x['captain_name']} ({x['captain_points']})" for x in worst_captains])
            best_bench_str = " | ".join([f"{x['manager']} ({x['bench_total_points']})" for x in best_benches])

            # Format transfer strings with colors
            def format_transfer_diff(diff):
                if diff > 0:
                    return f'<span style="color: #4caf50; font-weight: bold;">(+{diff})</span>'
                elif diff < 0:
                    return f'<span style="color: #f44336; font-weight: bold;">({diff})</span>'
                else:
                    return f'({diff})'

            # Format transfer strings (only if there are transfers)
            if best_transfers:
                best_transfer_str = " | ".join([f"{x['manager']} {format_transfer_diff(x['transfer_diff'])}" for x in best_transfers])
            else:
                best_transfer_str = "-"

            if worst_transfers:
                worst_transfer_str = " | ".join([f"{x['manager']} {format_transfer_diff(x['transfer_diff'])}" for x in worst_transfers])
            else:
                worst_transfer_str = "-"

            results.append({
                'GW': f"GW {gw}",
                'Best_Captain': best_captain_str,
                'Worst_Captain': worst_captain_str,
                'Best_Bench': best_bench_str,
                'Best_Transfer': best_transfer_str,
                'Worst_Transfer': worst_transfer_str
            })

    progress_bar.empty()
    status_text.empty()

    if not results:
        raise FPLError("Unable to fetch fun statistics data")

    return pd.DataFrame(results)

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
                     max_entries: Optional[int] = None, top_n: int = 5) -> pd.DataFrame:
    """
    Calculate top N most picked players
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

    # Sort and get top N
    result = result.sort_values('times_picked', ascending=False).head(top_n)

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
    # status_placeholder = st.empty()
    # status_placeholder.success(f"Auto-detected gameweek range: GW1 to GW{current_gw_end}")

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

def build_awards_summary_table(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Build awards summary table showing GW, Weekly_Wins, and Monthly_Wins
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['GW', 'Weekly_Wins', 'Monthly_Wins'])

    # Get available GWs
    available_gws = sorted(gw_points_df['GW'].unique())

    # Initialize results
    results = []

    # Process each GW
    for gw in available_gws:
        # Get weekly winner
        weekly_ranking = build_weekly_ranking(gw_points_df, gw)
        weekly_winner = ""

        if not weekly_ranking.empty:
            # Get the winner (rank 1 with lowest transfers if tied)
            winners = weekly_ranking[weekly_ranking['Rank'] == 1]
            if len(winners) > 0:
                weekly_winner = winners.iloc[0]['Manager']

        # Determine which month this GW belongs to
        month = month_mapping.get(gw, 1)

        results.append({
            'GW': gw,
            'Weekly_Wins': weekly_winner,
            'Month': month
        })

    # Convert to DataFrame
    awards_summary_df = pd.DataFrame(results)

    # Calculate monthly winners
    monthly_winners = {}
    available_months = sorted(set(month_mapping.values()))

    for month in available_months:
        monthly_ranking = build_monthly_ranking(gw_points_df, month_mapping, month)
        if not monthly_ranking.empty:
            # Get the winner (rank 1 with lowest transfers if tied)
            winners = monthly_ranking[monthly_ranking['Rank'] == 1]
            if len(winners) > 0:
                monthly_winners[month] = winners.iloc[0]['Manager']

    # Add monthly winners to the dataframe
    awards_summary_df['Monthly_Wins'] = awards_summary_df['Month'].map(monthly_winners).fillna("")

    # Drop the temporary Month column
    awards_summary_df = awards_summary_df.drop('Month', axis=1)

    return awards_summary_df

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
                # show_temporary_message("Data refreshed successfully!", "success")
                pass
            else:
                # First time loading
                # show_temporary_message("Data loaded and cached for faster access!", "info")
                pass

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

        # Add CSS for custom table styling
        st.markdown("""
        <style>
        /* Custom Table Styling */
        .custom-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            overflow: hidden;
        }

        .custom-table thead {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .custom-table th {
            padding: 15px 12px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 12px;
            border: none;
        }

        .custom-table tbody tr {
            border-bottom: 1px solid #e0e0e0;
            transition: all 0.3s ease;
        }

        .custom-table tbody tr:nth-child(even) {
            background-color: #f8f9fa;
        }

        .custom-table tbody tr:hover {
            background-color: #e3f2fd;
            transform: translateY(-1px);
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        .custom-table td {
            padding: 12px;
            border: none;
            vertical-align: middle;
        }

        /* Rank column styling */
        .rank-cell {
            font-weight: bold;
            color: #1976d2;
            background: linear-gradient(135deg, #e3f2fd, #bbdefb);
            text-align: center;
            border-radius: 4px;
            margin: 2px;
            padding: 8px !important;
        }

        /* Top 3 ranks special styling */
        .rank-1 {
            background: linear-gradient(135deg, #ffd700, #ffed4e) !important;
            color: #b8860b !important;
            font-weight: bold;
        }

        .rank-2 {
            background: linear-gradient(135deg, #c0c0c0, #e8e8e8) !important;
            color: #696969 !important;
            font-weight: bold;
        }

        .rank-3 {
            background: linear-gradient(135deg, #cd7f32, #daa520) !important;
            color: #8b4513 !important;
            font-weight: bold;
        }

        /* Manager and Team columns */
        .manager-cell {
            font-weight: 600;
            color: #2c3e50;
        }

        .team-cell {
            color: #34495e;
            font-style: italic;
        }

        /* Points columns */
        .points-cell {
            text-align: center;
            font-weight: 500;
        }

        .total-cell {
            font-weight: bold;
            color: #27ae60;
            background-color: #e8f5e8;
            text-align: center;
        }

        /* Transfers columns */
        .transfers-cell {
            text-align: center;
            color: #e74c3c;
            font-size: 12px;
        }

        /* Chip columns */
        .chip-cell {
            text-align: center;
            font-weight: 500;
            font-size: 12px;
            padding: 4px !important;
            vertical-align: middle;
        }

        /* Chip container styling */
        .chip-container {
            margin: 0 auto;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .chip-container:hover {
            transform: scale(1.05);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        }

        .chip-container img {
            transition: filter 0.2s ease;
        }

        /* Container for table */
        .table-container {
            overflow-x: auto;
            margin: 10px 0;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        /* Hyperlink styling for GW Points */
        .gw-points-link {
            color: #1976d2;
            text-decoration: none;
            font-weight: 500;
            padding: 4px 8px;
            border-radius: 4px;
            transition: all 0.3s ease;
            display: inline-block;
        }

        .gw-points-link:hover {
            background-color: #e3f2fd;
            color: #0d47a1;
            text-decoration: underline;
            transform: scale(1.05);
        }

        .gw-points-link:visited {
            color: #7b1fa2;
        }

        /* Fun Stats Table Styling */
        .gw-cell {
            background-color: #e8f5e8;
            font-weight: bold;
            text-align: center;
            color: #2e7d32;
        }

        .captain-cell {
            font-size: 13px;
            line-height: 1.4;
        }

        .bench-cell {
            background-color: #fff3e0;
            font-weight: 500;
            color: #ef6c00;
        }

        /* Fun stats specific styling */
        .custom-table tbody tr td.captain-cell {
            max-width: 300px;
            word-wrap: break-word;
            white-space: normal;
            line-height: 1.4;
            padding: 8px;
        }

        .custom-table tbody tr td.bench-cell {
            text-align: center;
            font-weight: bold;
            max-width: 200px;
            word-wrap: break-word;
            white-space: normal;
            line-height: 1.4;
            padding: 8px;
        }

        /* Handle multiple managers display */
        .custom-table tbody tr td.captain-cell,
        .custom-table tbody tr td.bench-cell {
            font-size: 13px;
        }

        /* Transfer table styling */
        .custom-table tbody tr td.transfer-cell {
            font-size: 12px;
            text-align: center;
            padding: 8px 4px;
            min-width: 120px;
            vertical-align: top;
            line-height: 1.4;
        }

        /* Awards summary table styling */
        .awards-summary-table {
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }

        .awards-summary-table th {
            background: linear-gradient(135deg, #ffd700 0%, #ffb347 100%);
            color: #333;
            font-weight: bold;
            text-align: center;
            padding: 12px;
            border: 1px solid #ddd;
        }

        .awards-summary-table td {
            text-align: center;
            padding: 10px;
            border: 1px solid #ddd;
            vertical-align: middle;
        }

        .awards-summary-table .monthly-winner-cell {
            background-color: #fff3cd;
            font-weight: bold;
            color: #856404;
            border-left: 3px solid #ffc107;
        }

        .awards-summary-table tr:nth-child(even) {
            background-color: #f8f9fa;
        }

        .awards-summary-table tr:hover {
            background-color: #e9ecef;
        }
        </style>
        """, unsafe_allow_html=True)

        # Tabs
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
            "👥 League Members",
            "📊 GW Points",
            "📅 Month Points",
            "⭐ Top Picks",
            "🏆 Rankings",
            "🏅 Awards Statistics",
            "🔄 Transfer",
            "🎯 Chip History",
            "🎉 Fun Stats"
        ])

        with tab1:
            st.subheader("League Members List")
            display_df = entries_df.copy()
            if max_entries:
                display_df = display_df.head(max_entries)

            # Prepare display dataframe: hide Team_ID
            display_df_formatted = display_df[['Rank', 'Manager', 'Team', 'Total']].copy()

            # Render custom table
            table_html = render_custom_table(display_df_formatted, "league")
            st.markdown(table_html, unsafe_allow_html=True)

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

                # Create team_id_mapping for hyperlinks
                team_id_mapping = {}
                if 'entries_df' in st.session_state:
                    entries_df = st.session_state.entries_df
                    team_id_mapping = dict(zip(entries_df['Manager'], entries_df['Team_ID']))

                # Render custom table with hyperlinks
                table_html = render_custom_table(display_df, "gw", team_id_mapping)
                st.markdown(table_html, unsafe_allow_html=True)

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

                    # Prepare display dataframe: hide Team_ID
                    display_cols = [col for col in month_points_df.columns if col != 'Team_ID']
                    display_df = month_points_df[display_cols].copy()

                    # Render custom table
                    table_html = render_custom_table(display_df, "month")
                    st.markdown(table_html, unsafe_allow_html=True)

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
            st.subheader("Top N Most Picked Players")

            # Options for top picks
            col1, col2, col3 = st.columns(3)
            with col1:
                single_gw = st.checkbox("Single GW only", value=False)
            with col2:
                if single_gw:
                    selected_gw = st.selectbox("Select GW", gw_range)
                    analysis_gw_range = [selected_gw]
                else:
                    analysis_gw_range = gw_range
            with col3:
                top_n = st.selectbox(
                    "Number of players",
                    options=[3, 5, 10, 15, 20, 25, 30],
                    index=1,  # Default to 5
                    help="Select how many top players to display"
                )

            if st.button("🔄 Calculate Top Picks", key="load_picks"):
                try:
                    with st.spinner("Calculating top picks..."):
                        top_picks_df = compute_top_picks(
                            entries_df,
                            analysis_gw_range,
                            bootstrap_df,
                            max_entries,
                            top_n
                        )

                    st.session_state.top_picks_df = top_picks_df

                except Exception as e:
                    st.error(f"Error calculating top picks: {str(e)}")

            if 'top_picks_df' in st.session_state:
                top_picks_df = st.session_state.top_picks_df

                if not top_picks_df.empty:
                    # Render custom table
                    table_html = render_custom_table(top_picks_df, "picks")
                    st.markdown(table_html, unsafe_allow_html=True)

                    # Download button
                    filename = f"fpl_{league_id}_top_picks.csv"
                    create_download_button(top_picks_df, filename, "📥 Download CSV", key="download_picks")

                    # Chart
                    st.subheader("📊 Top Picks Chart")
                    fig = px.bar(
                        top_picks_df,
                        x='Player',
                        y='Times_Picked',
                        title=f'Top {len(top_picks_df)} Most Picked Players',
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

                            # Render custom table
                            table_html = render_custom_table(weekly_ranking, "ranking")
                            st.markdown(table_html, unsafe_allow_html=True)

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
                            # Render custom table
                            table_html = render_custom_table(monthly_ranking, "ranking")
                            st.markdown(table_html, unsafe_allow_html=True)

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

                        # Build awards summary table
                        awards_summary_df = build_awards_summary_table(
                            st.session_state.gw_points_df,
                            month_mapping
                        )

                    # Display Awards Summary Table
                    if not awards_summary_df.empty:
                        st.markdown("### 📅 Weekly and Monthly Winners Summary")
                        st.markdown("This table shows the winner of each gameweek and month. Monthly winners are determined by total points across all gameweeks in that month.")

                        # Render awards summary table with merged cells
                        awards_summary_html = render_awards_summary_table(awards_summary_df, month_mapping)
                        st.markdown(awards_summary_html, unsafe_allow_html=True)

                        # Download button for awards summary
                        filename_summary = f"fpl_{league_id}_awards_summary.csv"
                        create_download_button(awards_summary_df, filename_summary, "📥 Download Awards Summary CSV", key="download_awards_summary")

                        st.markdown("---")

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

                        # Render custom table
                        table_html = render_custom_table(awards_df, "awards")
                        st.markdown(table_html, unsafe_allow_html=True)

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

        with tab7:
            st.subheader("Transfer History")

            # Auto-load Transfer data if not already loaded or if data was refreshed
            should_load_transfer_data = ('transfer_history_df' not in st.session_state) or refresh_data

            if should_load_transfer_data:
                try:
                    with st.spinner("Loading transfer data..."):
                        transfer_history_df = build_transfer_history_table(entries_df, bootstrap_df, max_entries)

                    if not transfer_history_df.empty:
                        # Group transfers by Manager, Team, and GW to combine multiple transfers
                        grouped_transfers = transfer_history_df.groupby(['Manager', 'Team', 'GW'])['Transfer'].apply(
                            lambda x: ' | '.join(x) if len(x) > 1 else x.iloc[0]
                        ).reset_index()

                        # Create pivot table for display
                        transfer_pivot = grouped_transfers.pivot_table(
                            index=['Manager', 'Team'],
                            columns='GW',
                            values='Transfer',
                            fill_value='-',
                            aggfunc='first'
                        )

                        # Rename columns to GW1, GW2, etc.
                        transfer_pivot.columns = [f'GW{col}' for col in transfer_pivot.columns]

                        # Reset index to get Manager and Team as columns
                        transfer_pivot = transfer_pivot.reset_index()

                        # Sort by Manager name alphabetically
                        transfer_pivot = transfer_pivot.sort_values('Manager')

                        # Get available GWs from the data
                        available_gws = sorted([int(col.replace('GW', '')) for col in transfer_pivot.columns if col.startswith('GW')])

                        # Reorder columns to have Manager, Team first
                        gw_cols = ['Manager', 'Team'] + [f'GW{gw}' for gw in available_gws]
                        transfer_pivot = transfer_pivot[gw_cols]

                        st.session_state.transfer_history_df = transfer_history_df
                        st.session_state.transfer_display_df = transfer_pivot
                    else:
                        # Create empty display dataframe
                        st.session_state.transfer_history_df = pd.DataFrame()
                        st.session_state.transfer_display_df = pd.DataFrame(columns=['Manager', 'Team'])

                except Exception as e:
                    st.error(f"Error loading transfer data: {str(e)}")

            if 'transfer_display_df' in st.session_state and not st.session_state.transfer_display_df.empty:
                display_df = st.session_state.transfer_display_df.copy()

                # Create team_id_mapping for potential future use
                team_id_mapping = {}
                if 'entries_df' in st.session_state:
                    entries_df = st.session_state.entries_df
                    team_id_mapping = dict(zip(entries_df['Manager'], entries_df['Team_ID']))

                # Render custom table
                table_html = render_custom_table(display_df, "transfer", team_id_mapping)
                st.markdown(table_html, unsafe_allow_html=True)

                # Download button
                filename = f"fpl_{league_id}_transfer_history.csv"
                flat_df = st.session_state.transfer_history_df
                create_download_button(flat_df, filename, "📥 Download CSV", key="download_transfer")

                # Add transfer statistics
                st.markdown("---")
                st.subheader("📊 Transfer Statistics")

                try:
                    transfer_data = st.session_state.transfer_history_df

                    if not transfer_data.empty:
                        # Transfer activity by GW
                        st.markdown("#### 🔄 Transfer Activity by Gameweek")

                        col1, col2 = st.columns(2)

                        with col1:
                            # Transfer count by GW
                            gw_transfer_counts = transfer_data.groupby('GW').size()
                            fig = px.bar(
                                x=gw_transfer_counts.index,
                                y=gw_transfer_counts.values,
                                title="Number of Transfers by Gameweek",
                                labels={'x': 'Gameweek', 'y': 'Number of Transfers'}
                            )
                            fig.update_layout(height=400)
                            st.plotly_chart(fig, use_container_width=True)

                        with col2:
                            # Most active managers
                            manager_transfer_counts = transfer_data.groupby('Manager').size().sort_values(ascending=False).head(10)
                            fig2 = px.bar(
                                x=manager_transfer_counts.values,
                                y=manager_transfer_counts.index,
                                orientation='h',
                                title="Most Active Managers (Top 10)",
                                labels={'x': 'Number of Transfers', 'y': 'Manager'}
                            )
                            fig2.update_layout(height=400)
                            st.plotly_chart(fig2, use_container_width=True)

                        # Summary metrics
                        st.markdown("#### 📈 Summary Metrics")
                        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

                        with metric_col1:
                            total_transfers = len(transfer_data)
                            st.metric("Total Transfers", total_transfers)

                        with metric_col2:
                            unique_managers = transfer_data['Manager'].nunique()
                            st.metric("Managers Made Transfers", unique_managers)

                        with metric_col3:
                            avg_transfers_per_manager = total_transfers / unique_managers if unique_managers > 0 else 0
                            st.metric("Avg Transfers/Manager", f"{avg_transfers_per_manager:.1f}")

                        with metric_col4:
                            if not transfer_data.empty:
                                most_active_gw = transfer_data.groupby('GW').size().idxmax()
                                st.metric("Most Active GW", f"GW{most_active_gw}")

                        # Most transferred players
                        st.markdown("#### ⭐ Most Transferred Players")

                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("**Most Transferred IN**")
                            players_in = transfer_data['Player_In'].value_counts().head(10)
                            if not players_in.empty:
                                for i, (player, count) in enumerate(players_in.items(), 1):
                                    st.write(f"{i}. **{player}** - {count} times")
                            else:
                                st.info("No transfer data available")

                        with col2:
                            st.markdown("**Most Transferred OUT**")
                            players_out = transfer_data['Player_Out'].value_counts().head(10)
                            if not players_out.empty:
                                for i, (player, count) in enumerate(players_out.items(), 1):
                                    st.write(f"{i}. **{player}** - {count} times")
                            else:
                                st.info("No transfer data available")

                    else:
                        st.info("No transfer data available yet this season.")

                except Exception as e:
                    st.error(f"Error creating transfer statistics: {str(e)}")
            else:
                st.info("No transfer data available. This could be because:")
                st.markdown("""
                - The season hasn't started yet
                - No managers have made any transfers
                - Transfer data is still loading

                **Note**: Transfer data will be automatically loaded when you refresh the data or when transfers are made during the season.
                """)

        with tab8:
            st.subheader("Chip Usage History")

            # Auto-load Chip History data if not already loaded or if data was refreshed
            should_load_chip_data = ('chip_history_df' not in st.session_state) or refresh_data

            if should_load_chip_data:
                try:
                    with st.spinner("Loading chip usage data..."):
                        chip_history_df = build_chip_history_table(entries_df, gw_range, max_entries)

                    # Create pivot table for display
                    chip_pivot = chip_history_df.pivot_table(
                        index=['Manager', 'Team'],
                        columns='GW',
                        values='Active_Chip',
                        fill_value='-',
                        aggfunc='first'
                    )

                    # Rename columns to GW1, GW2, etc.
                    chip_pivot.columns = [f'GW{col}' for col in chip_pivot.columns]

                    # Reset index to get Manager and Team as columns
                    chip_pivot = chip_pivot.reset_index()

                    # Sort by Manager name alphabetically
                    chip_pivot = chip_pivot.sort_values('Manager')

                    # Reorder columns to have Manager, Team first (without Rank)
                    gw_cols = ['Manager', 'Team'] + [f'GW{gw}' for gw in sorted(gw_range)]
                    chip_pivot = chip_pivot[gw_cols]

                    st.session_state.chip_history_df = chip_history_df
                    st.session_state.chip_display_df = chip_pivot

                except Exception as e:
                    st.error(f"Error loading chip data: {str(e)}")

            if 'chip_display_df' in st.session_state:
                display_df = st.session_state.chip_display_df.copy()

                # Create team_id_mapping for potential future use
                team_id_mapping = {}
                if 'entries_df' in st.session_state:
                    entries_df = st.session_state.entries_df
                    team_id_mapping = dict(zip(entries_df['Manager'], entries_df['Team_ID']))

                # Render custom table
                table_html = render_custom_table(display_df, "chip", team_id_mapping)
                st.markdown(table_html, unsafe_allow_html=True)

                # Download button
                filename = f"fpl_{league_id}_chip_history.csv"
                flat_df = st.session_state.chip_history_df
                create_download_button(flat_df, filename, "📥 Download CSV", key="download_chip")

                # Add chip usage statistics
                st.markdown("---")
                st.subheader("📊 Chip Usage Statistics")

                try:
                    chip_data = st.session_state.chip_history_df

                    # Filter out entries with no chips used
                    chip_data_used = chip_data[chip_data['Active_Chip'] != '-']

                    if not chip_data_used.empty:
                        # Count chip usage by type
                        chip_counts = chip_data_used['Active_Chip'].value_counts()

                        # Display chip usage summary
                        st.markdown("#### 🎯 Chip Usage Summary")

                        col1, col2 = st.columns(2)

                        with col1:
                            # Chip usage bar chart
                            fig = px.bar(
                                x=chip_counts.index,
                                y=chip_counts.values,
                                title="Chip Usage Count",
                                labels={'x': 'Chip Type', 'y': 'Times Used'}
                            )
                            fig.update_layout(height=400)
                            st.plotly_chart(fig, use_container_width=True)

                        with col2:
                            # Chip usage by GW
                            gw_chip_usage = chip_data_used.groupby('GW')['Active_Chip'].count()
                            fig2 = px.line(
                                x=gw_chip_usage.index,
                                y=gw_chip_usage.values,
                                title="Chip Usage by Gameweek",
                                labels={'x': 'Gameweek', 'y': 'Number of Chips Used'},
                                markers=True
                            )
                            fig2.update_layout(height=400)
                            st.plotly_chart(fig2, use_container_width=True)

                        # Summary metrics
                        st.markdown("#### 📈 Summary Metrics")
                        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

                        with metric_col1:
                            total_chips_used = len(chip_data_used)
                            st.metric("Total Chips Used", total_chips_used)

                        with metric_col2:
                            unique_chip_types = len(chip_counts)
                            st.metric("Different Chip Types", unique_chip_types)

                        with metric_col3:
                            managers_used_chips = chip_data_used['Manager'].nunique()
                            st.metric("Managers Used Chips", managers_used_chips)

                        with metric_col4:
                            if len(chip_counts) > 0:
                                most_popular_chip = chip_counts.index[0]
                                st.metric("Most Popular Chip", most_popular_chip)
                    else:
                        st.info("No chips have been used yet this season.")

                except Exception as e:
                    st.error(f"Error creating chip statistics: {str(e)}")
            else:
                st.info("Chip data is loading...")

        with tab9:
            st.subheader("Fun Statistics by Gameweek")

            # Auto-load Fun Stats data if not already loaded or if data was refreshed
            should_load_fun_stats = ('fun_stats_df' not in st.session_state) or refresh_data

            if should_load_fun_stats:
                try:
                    with st.spinner("Loading fun statistics data..."):
                        fun_stats_df = build_fun_stats_table(entries_df, gw_range, bootstrap_df, max_entries)

                    st.session_state.fun_stats_df = fun_stats_df

                except Exception as e:
                    st.error(f"Error loading fun statistics: {str(e)}")

            if 'fun_stats_df' in st.session_state:
                display_df = st.session_state.fun_stats_df.copy()

                # Create team_id_mapping for potential future use
                team_id_mapping = {}
                if 'entries_df' in st.session_state:
                    entries_df = st.session_state.entries_df
                    team_id_mapping = dict(zip(entries_df['Manager'], entries_df['Team_ID']))

                # Render custom table
                table_html = render_custom_table(display_df, "fun_stats", team_id_mapping)
                st.markdown(table_html, unsafe_allow_html=True)

                # Download button
                filename = f"fpl_{league_id}_fun_stats.csv"
                create_download_button(display_df, filename, "📥 Download CSV", key="download_fun_stats")

                # Add some fun insights
                st.markdown("---")
                st.subheader("📊 Fun Insights")

                try:
                    fun_data = st.session_state.fun_stats_df

                    if not fun_data.empty:
                        # Extract manager names from the stats (handle multiple managers per entry)
                        best_captains = []
                        worst_captains = []
                        best_benches = []
                        best_transfers = []
                        worst_transfers = []

                        for _, row in fun_data.iterrows():
                            # Extract manager names (handle multiple managers separated by " | ")
                            best_cap_entries = row['Best_Captain'].split(' | ')
                            worst_cap_entries = row['Worst_Captain'].split(' | ')
                            best_bench_entries = row['Best_Bench'].split(' | ')

                            # Handle transfer columns if they exist and are not "-"
                            if 'Best_Transfer' in row and pd.notna(row['Best_Transfer']) and str(row['Best_Transfer']).strip() != '-':
                                best_transfer_entries = row['Best_Transfer'].split(' | ')
                                for entry in best_transfer_entries:
                                    if entry.strip() != '-':  # Skip "-" entries
                                        # Remove HTML tags and extract manager name
                                        import re
                                        clean_entry = re.sub(r'<[^>]+>', '', entry)
                                        manager_name = clean_entry.split(' (')[0]
                                        best_transfers.append(manager_name)

                            if 'Worst_Transfer' in row and pd.notna(row['Worst_Transfer']) and str(row['Worst_Transfer']).strip() != '-':
                                worst_transfer_entries = row['Worst_Transfer'].split(' | ')
                                for entry in worst_transfer_entries:
                                    if entry.strip() != '-':  # Skip "-" entries
                                        # Remove HTML tags and extract manager name
                                        import re
                                        clean_entry = re.sub(r'<[^>]+>', '', entry)
                                        manager_name = clean_entry.split(' (')[0]
                                        worst_transfers.append(manager_name)

                            # Extract manager names from each entry
                            for entry in best_cap_entries:
                                manager_name = entry.split(' - ')[0]
                                best_captains.append(manager_name)

                            for entry in worst_cap_entries:
                                manager_name = entry.split(' - ')[0]
                                worst_captains.append(manager_name)

                            for entry in best_bench_entries:
                                manager_name = entry.split(' (')[0]
                                best_benches.append(manager_name)

                        # Count occurrences
                        from collections import Counter
                        best_cap_counts = Counter(best_captains)
                        worst_cap_counts = Counter(worst_captains)
                        best_bench_counts = Counter(best_benches)
                        best_transfer_counts = Counter(best_transfers)
                        worst_transfer_counts = Counter(worst_transfers)

                        # Display insights
                        col1, col2, col3, col4, col5 = st.columns(5)

                        with col1:
                            st.markdown("#### 🏆 Captain King")
                            if best_cap_counts:
                                max_count = best_cap_counts.most_common(1)[0][1]
                                top_managers = [manager for manager, count in best_cap_counts.items() if count == max_count]
                                managers_str = " | ".join(top_managers)
                                st.metric("Best Captain Manager(s)",
                                         managers_str,
                                         f"{max_count} times")

                        with col2:
                            st.markdown("#### 😅 Captain... Unlucky")
                            if worst_cap_counts:
                                max_count = worst_cap_counts.most_common(1)[0][1]
                                worst_managers = [manager for manager, count in worst_cap_counts.items() if count == max_count]
                                managers_str = " | ".join(worst_managers)
                                st.metric("Worst Captain Manager(s)",
                                         managers_str,
                                         f"{max_count} times")

                        with col3:
                            st.markdown("#### 🔄 Bench Expert")
                            if best_bench_counts:
                                max_count = best_bench_counts.most_common(1)[0][1]
                                bench_managers = [manager for manager, count in best_bench_counts.items() if count == max_count]
                                managers_str = " | ".join(bench_managers)
                                st.metric("Best Bench Manager(s)",
                                         managers_str,
                                         f"{max_count} times")

                        with col4:
                            st.markdown("#### 📈 Transfer Master")
                            if best_transfer_counts:
                                max_count = best_transfer_counts.most_common(1)[0][1]
                                transfer_managers = [manager for manager, count in best_transfer_counts.items() if count == max_count]
                                managers_str = " | ".join(transfer_managers)
                                st.metric("Best Transfer Manager(s)",
                                         managers_str,
                                         f"{max_count} times")

                        with col5:
                            st.markdown("#### 📉 Transfer... Oops")
                            if worst_transfer_counts:
                                max_count = worst_transfer_counts.most_common(1)[0][1]
                                worst_transfer_managers = [manager for manager, count in worst_transfer_counts.items() if count == max_count]
                                managers_str = " | ".join(worst_transfer_managers)
                                st.metric("Worst Transfer Manager(s)",
                                         managers_str,
                                         f"{max_count} times")

                        # Fun facts
                        st.markdown("#### 🎯 Fun Facts")

                        total_gws = len(fun_data)
                        unique_best_captains = len(set(best_captains))
                        unique_worst_captains = len(set(worst_captains))
                        unique_best_benches = len(set(best_benches))
                        unique_best_transfers = len(set(best_transfers))
                        unique_worst_transfers = len(set(worst_transfers))

                        fact_col1, fact_col2, fact_col3 = st.columns(3)

                        with fact_col1:
                            st.info(f"📈 {unique_best_captains}/{len(entries_df)} managers had best captain of the week")
                            st.info(f"📉 {unique_worst_captains}/{len(entries_df)} managers had worst captain of the week")

                        with fact_col2:
                            st.info(f"🔄 {unique_best_benches}/{len(entries_df)} managers had best bench of the week")
                            if total_gws > 0:
                                diversity_score = (unique_best_captains + unique_worst_captains + unique_best_benches) / (3 * total_gws) * 100
                                st.info(f"🎲 Statistics diversity: {diversity_score:.1f}%")

                        with fact_col3:
                            st.info(f"📈 {unique_best_transfers}/{len(entries_df)} managers had best transfer of the week")
                            st.info(f"📉 {unique_worst_transfers}/{len(entries_df)} managers had worst transfer of the week")
                    else:
                        st.info("No fun statistics data available yet.")

                except Exception as e:
                    st.error(f"Error creating fun insights: {str(e)}")
            else:
                st.info("Fun statistics data is loading...")

    else:
        st.info("👆 Please configure settings in the sidebar")

if __name__ == "__main__":
    main()