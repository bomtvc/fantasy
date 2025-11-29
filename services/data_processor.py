"""
Data Processor Service
Business logic for FPL data calculations and aggregations
"""

import pandas as pd
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import config
from .fpl_api import (
    FPLError,
    get_entry_history,
    get_entry_transfers,
    get_entry_gw_picks,
    get_player_gw_points
)


def parse_month_mapping(mapping_str: str) -> Dict[int, int]:
    """
    Parse month mapping string to dict {gw: month}
    Example: "1-4,5-9,10-13" -> {1:1, 2:1, 3:1, 4:1, 5:2, 6:2, ...}
    
    Args:
        mapping_str: Comma-separated ranges (e.g., "1-4,5-8,9-12")
        
    Returns:
        Dict mapping GW number to month number
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
        print(f"Error parsing month mapping: {str(e)}")
        return {}
    
    return gw_to_month


def build_gw_points_table(entries_df: pd.DataFrame, gw_range: List[int], 
                          max_entries: Optional[int] = None,
                          progress_callback=None) -> pd.DataFrame:
    """
    Build gameweek points table for all entries using optimized history API
    
    Args:
        entries_df: DataFrame with league entries
        gw_range: List of gameweek numbers to process
        max_entries: Optional limit on number of entries
        progress_callback: Optional callback function(current, total, message)
        
    Returns:
        DataFrame with GW points data for all entries
        
    Raises:
        FPLError: If unable to fetch points data for any entry
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)
    
    results = []
    total_requests = len(entries_df)
    
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        # Submit all tasks - one per entry instead of per entry per GW
        future_to_info = {}
        for _, entry in entries_df.iterrows():
            future = executor.submit(get_entry_history, entry['Team_ID'])
            future_to_info[future] = (entry['Team_ID'], entry['Manager'], entry['Team'])
        
        # Collect results
        completed = 0
        for future in as_completed(future_to_info):
            team_id, manager, team = future_to_info[future]
            completed += 1
            
            # Update progress
            if progress_callback:
                progress = completed / total_requests
                progress_callback(completed, total_requests, 
                                f"Fetching data: {completed}/{total_requests} ({progress:.1%})")
            
            try:
                data = future.result()
                if data and 'current' in data:
                    # Process all gameweeks for this entry
                    for event in data['current']:
                        gw = event.get('event')
                        # Ensure GW is integer to avoid type comparison errors
                        if gw is not None:
                            gw = int(gw)
                        if gw in gw_range:
                            results.append({
                                'Team_ID': team_id,
                                'Manager': manager,
                                'Team': team,
                                'GW': int(gw),  # Ensure integer type
                                'Points': event.get('points', 0),
                                'Total_Points': event.get('total_points', 0),
                                'Transfers': event.get('event_transfers', 0),
                                'Transfer_Cost': event.get('event_transfers_cost', 0),
                                'Bench_Points': event.get('points_on_bench', 0),
                                'picks': []  # Will be empty since we're not fetching picks
                            })
                    
                    # Add missing GWs with default values
                    existing_gws = {int(event.get('event')) for event in data['current'] if event.get('event') is not None}
                    for gw in gw_range:
                        if gw not in existing_gws:
                            results.append({
                                'Team_ID': team_id,
                                'Manager': manager,
                                'Team': team,
                                'GW': int(gw),  # Ensure integer type
                                'Points': 0,
                                'Total_Points': 0,
                                'Transfers': 0,
                                'Transfer_Cost': 0,
                                'Bench_Points': 0,
                                'picks': []
                            })
                else:
                    # Add rows with default values if no data
                    for gw in gw_range:
                        results.append({
                            'Team_ID': team_id,
                            'Manager': manager,
                            'Team': team,
                            'GW': int(gw),  # Ensure integer type
                            'Points': 0,
                            'Total_Points': 0,
                            'Transfers': 0,
                            'Transfer_Cost': 0,
                            'Bench_Points': 0,
                            'picks': []
                        })
            except Exception as e:
                print(f"Warning: Error processing entry {team_id}: {str(e)}")
                # Add default values for all GWs for this entry
                for gw in gw_range:
                    results.append({
                        'Team_ID': team_id,
                        'Manager': manager,
                        'Team': team,
                        'GW': int(gw),  # Ensure integer type
                        'Points': 0,
                        'Total_Points': 0,
                        'Transfers': 0,
                        'Transfer_Cost': 0,
                        'Bench_Points': 0,
                        'picks': []
                    })
            
            # Small delay to avoid rate limit
            time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)
    
    if not results:
        raise FPLError("Unable to fetch points data for any entry")
    
    return pd.DataFrame(results)


def build_month_points_table(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Build month points table from GW data (excluding incomplete months)
    
    Args:
        gw_points_df: DataFrame with GW points data
        month_mapping: Dict mapping GW to month number
        
    Returns:
        DataFrame with monthly points aggregated
    """
    # Add month column to dataframe
    gw_points_df = gw_points_df.copy()
    gw_points_df['Month'] = gw_points_df['GW'].map(month_mapping)
    
    # Ensure Month is integer type (where not null) to avoid comparison errors
    gw_points_df['Month'] = gw_points_df['Month'].apply(lambda x: int(x) if pd.notna(x) else x)
    
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
    
    # Group by entry and month, sum points and transfer costs
    month_summary = month_df.groupby(['Team_ID', 'Manager', 'Team', 'Month']).agg({
        'Points': 'sum',
        'Transfers': 'sum',
        'Transfer_Cost': 'sum'
    }).reset_index()
    
    # Pivot to have column for each month
    pivot_points = month_summary.pivot_table(
        index=['Team_ID', 'Manager', 'Team'],
        columns='Month',
        values='Points',
        fill_value=0
    )
    
    pivot_transfer_costs = month_summary.pivot_table(
        index=['Team_ID', 'Manager', 'Team'],
        columns='Month',
        values='Transfer_Cost',
        fill_value=0
    )
    
    # Create column names for months
    month_cols = [f"Month_{int(col)}" for col in pivot_points.columns]
    pivot_points.columns = month_cols
    pivot_transfer_costs.columns = month_cols
    
    # Add total column: Total = Sum(Points) - Sum(Transfer_Cost)
    total_points = pivot_points.sum(axis=1)
    total_transfer_costs = pivot_transfer_costs.sum(axis=1)
    pivot_points['Total'] = total_points - total_transfer_costs
    
    # Reset index for export
    result = pivot_points.reset_index()
    
    return result


def build_month_points_table_full(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Build month points table from GW data (including all weeks, even with 0 points)
    This is used for Month Points tab to show complete monthly statistics
    
    Args:
        gw_points_df: DataFrame with GW points data
        month_mapping: Dict mapping GW to month number
        
    Returns:
        DataFrame with full monthly points including transfer info
    """
    # Add month column to dataframe
    gw_points_df = gw_points_df.copy()
    gw_points_df['Month'] = gw_points_df['GW'].map(month_mapping)
    
    # Ensure Month is integer type (where not null) to avoid comparison errors
    gw_points_df['Month'] = gw_points_df['Month'].apply(lambda x: int(x) if pd.notna(x) else x)
    
    # Remove GWs not in mapping
    month_df = gw_points_df.dropna(subset=['Month'])
    
    if month_df.empty:
        return pd.DataFrame(columns=['Team_ID', 'Manager', 'Team', 'Total'])
    
    # Group by entry and month, sum points and transfer costs (including 0 points)
    month_summary = month_df.groupby(['Team_ID', 'Manager', 'Team', 'Month']).agg({
        'Points': 'sum',
        'Transfers': 'sum',
        'Transfer_Cost': 'sum'
    }).reset_index()
    
    # Pivot to have column for each month
    pivot_points = month_summary.pivot_table(
        index=['Team_ID', 'Manager', 'Team'],
        columns='Month',
        values='Points',
        fill_value=0
    )
    
    pivot_transfers = month_summary.pivot_table(
        index=['Team_ID', 'Manager', 'Team'],
        columns='Month',
        values='Transfers',
        fill_value=0
    )
    
    pivot_transfer_costs = month_summary.pivot_table(
        index=['Team_ID', 'Manager', 'Team'],
        columns='Month',
        values='Transfer_Cost',
        fill_value=0
    )
    
    # Create column names for months
    month_cols = [f"Month_{int(col)}" for col in pivot_points.columns]
    pivot_points.columns = month_cols
    pivot_transfers.columns = month_cols
    pivot_transfer_costs.columns = month_cols
    
    # Reset index for all pivots
    points_df = pivot_points.reset_index()
    transfers_df = pivot_transfers.reset_index()
    transfer_costs_df = pivot_transfer_costs.reset_index()
    
    # Merge all dataframes
    result = points_df.copy()
    
    # Add transfer data
    for month_col in month_cols:
        # Get transfer and cost data for this month
        transfer_data = transfers_df[['Team_ID', 'Manager', 'Team', month_col]]
        cost_data = transfer_costs_df[['Team_ID', 'Manager', 'Team', month_col]]
        
        # Merge transfer data
        result = result.merge(
            transfer_data.rename(columns={month_col: f"{month_col}_transfers_raw"}),
            on=['Team_ID', 'Manager', 'Team'],
            how='left'
        )
        
        # Merge cost data
        result = result.merge(
            cost_data.rename(columns={month_col: f"{month_col}_costs_raw"}),
            on=['Team_ID', 'Manager', 'Team'],
            how='left'
        )
        
        # Create formatted transfer column
        transfer_col = f"{month_col}_Transfers"
        transfers_raw_col = f"{month_col}_transfers_raw"
        costs_raw_col = f"{month_col}_costs_raw"
        
        def format_month_transfer(row):
            transfers = int(row[transfers_raw_col]) if pd.notna(row[transfers_raw_col]) else 0
            cost = int(row[costs_raw_col]) if pd.notna(row[costs_raw_col]) else 0
            if transfers == 0:
                return "-"
            elif cost == 0:
                return str(transfers)
            else:
                return f"{transfers}(-{cost})"
        
        result[transfer_col] = result.apply(format_month_transfer, axis=1)
        
        # Remove the raw columns
        result = result.drop(columns=[transfers_raw_col, costs_raw_col])
    
    # Add total column: Total = Sum(Points) - Sum(Transfer_Cost)
    total_points = points_df[month_cols].sum(axis=1)
    total_transfer_costs = transfer_costs_df[month_cols].sum(axis=1)
    result['Total'] = total_points - total_transfer_costs
    
    # Add Rank column based on Total points (descending)
    result = result.sort_values('Total', ascending=False)
    result['Rank'] = range(1, len(result) + 1)
    
    # Reorder columns to have Rank first, then interleave Month_X and Month_X_Transfers
    cols = ['Rank', 'Team_ID', 'Manager', 'Team']
    
    # Get month columns and sort them properly by extracting the numeric part
    month_point_cols = [col for col in result.columns if col.startswith('Month_') and not col.endswith('_Transfers')]
    # Sort by the numeric part after 'Month_'
    month_point_cols_sorted = sorted(month_point_cols, key=lambda x: int(x.split('_')[1]))
    
    for month_col in month_point_cols_sorted:
        cols.append(month_col)
        transfer_col = f"{month_col}_Transfers"
        if transfer_col in result.columns:
            cols.append(transfer_col)
    cols.append('Total')
    result = result[cols]
    
    return result


def build_transfer_history_table(entries_df: pd.DataFrame, bootstrap_df: pd.DataFrame, 
                                 max_entries: Optional[int] = None,
                                 progress_callback=None) -> pd.DataFrame:
    """
    Build transfer history table for all entries showing transfers by gameweek
    
    Args:
        entries_df: DataFrame with league entries
        bootstrap_df: DataFrame with player data
        max_entries: Optional limit on number of entries
        progress_callback: Optional callback function(current, total, message)
        
    Returns:
        DataFrame with transfer history
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)
    
    results = []
    total_requests = len(entries_df)
    
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
            if progress_callback:
                progress = completed / total_requests
                progress_callback(completed, total_requests,
                                f"Fetching transfer data: {completed}/{total_requests} ({progress:.1%})")
            
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
            except Exception as e:
                print(f"Warning: Error processing transfers for entry {team_id}: {str(e)}")
            
            # Small delay to avoid rate limit
            time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)
    
    if not results:
        # Return empty dataframe with proper columns if no transfers found
        return pd.DataFrame(columns=['Team_ID', 'Manager', 'Team', 'GW', 'Transfer', 
                                    'Player_In', 'Player_Out', 'Player_In_Points', 'Player_Out_Points'])
    
    return pd.DataFrame(results)


def get_entry_chips_optimized(entry_id: int, gw_range: List[int]) -> Dict[int, str]:
    """
    Get chip usage for an entry across multiple GWs with minimal API calls
    
    Args:
        entry_id: FPL team entry ID
        gw_range: List of gameweek numbers
        
    Returns:
        Dict mapping GW to chip name
    """
    chips = {}
    
    # Try to get chip info from history first (if available in future API updates)
    try:
        history_data = get_entry_history(entry_id)
        if history_data and 'chips' in history_data:
            for chip in history_data['chips']:
                event = chip.get('event')
                chip_name = chip.get('name')
                if event in gw_range:
                    chips[event] = chip_name
    except:
        pass
    
    # For missing chip data, we still need to check picks API for active chips
    # But we'll batch this more efficiently
    missing_gws = [gw for gw in gw_range if gw not in chips]
    
    for gw in missing_gws:
        try:
            data = get_entry_gw_picks(entry_id, gw)
            active_chip = data.get('active_chip') if data else None
            chips[gw] = active_chip if active_chip else '-'
            time.sleep(config.REQUEST_DELAY / 4)  # Reduced delay
        except:
            chips[gw] = '-'
    
    return chips


def build_chip_history_table(entries_df: pd.DataFrame, gw_range: List[int], 
                             max_entries: Optional[int] = None,
                             progress_callback=None) -> pd.DataFrame:
    """
    Build chip history table for all entries showing which chips were used in each GW
    
    Args:
        entries_df: DataFrame with league entries
        gw_range: List of gameweek numbers
        max_entries: Optional limit on number of entries
        progress_callback: Optional callback function(current, total, message)
        
    Returns:
        DataFrame with chip usage history
        
    Raises:
        FPLError: If unable to fetch chip data for any entry
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)
    
    results = []
    total_requests = len(entries_df)
    
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        # Submit all tasks - one per entry instead of per entry per GW
        future_to_info = {}
        for _, entry in entries_df.iterrows():
            future = executor.submit(get_entry_chips_optimized, entry['Team_ID'], gw_range)
            future_to_info[future] = (entry['Team_ID'], entry['Manager'], entry['Team'])
        
        # Collect results
        completed = 0
        for future in as_completed(future_to_info):
            team_id, manager, team = future_to_info[future]
            completed += 1
            
            # Update progress
            if progress_callback:
                progress = completed / total_requests
                progress_callback(completed, total_requests,
                                f"Fetching chip data: {completed}/{total_requests} ({progress:.1%})")
            
            try:
                chips_data = future.result()
                for gw in gw_range:
                    active_chip = chips_data.get(gw, '-')
                    results.append({
                        'Team_ID': team_id,
                        'Manager': manager,
                        'Team': team,
                        'GW': gw,
                        'Active_Chip': active_chip
                    })
            except Exception as e:
                print(f"Warning: Error processing entry {team_id}: {str(e)}")
                for gw in gw_range:
                    results.append({
                        'Team_ID': team_id,
                        'Manager': manager,
                        'Team': team,
                        'GW': gw,
                        'Active_Chip': '-'
                    })
            
            # Small delay to avoid rate limit
            time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)
    
    if not results:
        raise FPLError("Unable to fetch chip data for any entry")

    return pd.DataFrame(results)


def calculate_awards_statistics(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Calculate awards statistics for all managers

    Args:
        gw_points_df: GW points DataFrame with columns [Team_ID, Manager, Team, GW, Points]
        month_mapping: Dict mapping GW number to month number

    Returns:
        DataFrame with columns [Team_ID, Manager, Team, Weekly_Wins, Monthly_Wins, Total_Prize_Money]
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['Team_ID', 'Manager', 'Team', 'Weekly_Wins', 'Monthly_Wins', 'Total_Prize_Money'])

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
            'Monthly_Wins': 0,
            'Weekly_Prize_Money': 0.0,
            'Monthly_Prize_Money': 0.0
        })

    awards_df = pd.DataFrame(awards_data)

    # Prize money constants
    WEEKLY_PRIZE = 300000  # $300,000 for weekly winner
    MONTHLY_PRIZE = 500000  # $500,000 for monthly winner

    # Calculate weekly wins (1st place in each GW)
    available_gws = sorted(gw_points_df['GW'].unique())

    for gw in available_gws:
        gw_data = gw_points_df[gw_points_df['GW'] == gw]
        if not gw_data.empty:
            max_points = gw_data['Points'].max()
            winners = gw_data[gw_data['Points'] == max_points]
            num_winners = len(winners)
            prize_per_winner = WEEKLY_PRIZE / num_winners

            for _, winner in winners.iterrows():
                team_id = winner['Team_ID']
                awards_df.loc[awards_df['Team_ID'] == team_id, 'Weekly_Wins'] += 1
                awards_df.loc[awards_df['Team_ID'] == team_id, 'Weekly_Prize_Money'] += prize_per_winner

    # Calculate monthly wins (1st place in each month based on total points)
    available_months = sorted(set(month_mapping.values()))

    for month in available_months:
        # Get GWs for this month
        month_gws = [gw for gw, m in month_mapping.items() if m == month]
        month_data = gw_points_df[gw_points_df['GW'].isin(month_gws)]

        if not month_data.empty:
            # Calculate total points per manager for this month
            month_totals = month_data.groupby(['Team_ID', 'Manager', 'Team'])['Points'].sum().reset_index()

            if not month_totals.empty:
                max_points = month_totals['Points'].max()
                winners = month_totals[month_totals['Points'] == max_points]
                num_winners = len(winners)
                prize_per_winner = MONTHLY_PRIZE / num_winners

                for _, winner in winners.iterrows():
                    team_id = winner['Team_ID']
                    awards_df.loc[awards_df['Team_ID'] == team_id, 'Monthly_Wins'] += 1
                    awards_df.loc[awards_df['Team_ID'] == team_id, 'Monthly_Prize_Money'] += prize_per_winner

    # Calculate total prize money
    awards_df['Total_Prize_Money'] = awards_df['Weekly_Prize_Money'] + awards_df['Monthly_Prize_Money']

    # Keep only needed columns
    result = awards_df[['Team_ID', 'Manager', 'Team', 'Weekly_Wins', 'Monthly_Wins', 'Total_Prize_Money']]

    return result


def create_ranking_table(data_df: pd.DataFrame, score_column: str) -> pd.DataFrame:
    """
    Create ranking table with medals for top 3

    Args:
        data_df: DataFrame with data to rank
        score_column: Column name to use for ranking

    Returns:
        DataFrame with Medal, Rank columns added
    """
    # Sort by score descending
    ranked_df = data_df.sort_values(score_column, ascending=False).reset_index(drop=True)

    # Create ranking with ties handling
    ranked_df['Rank'] = 1
    current_rank = 1

    for i in range(1, len(ranked_df)):
        prev_score = ranked_df.loc[i-1, score_column]
        curr_score = ranked_df.loc[i, score_column]

        if curr_score != prev_score:
            current_rank = i + 1

        ranked_df.loc[i, 'Rank'] = current_rank

    # Add medal column
    def get_medal(rank):
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
    Build weekly ranking for selected GW

    Args:
        gw_points_df: GW points DataFrame
        selected_gw: Selected gameweek number

    Returns:
        DataFrame with weekly ranking
    """
    # Filter for selected GW
    gw_data = gw_points_df[gw_points_df['GW'] == selected_gw].copy()

    if gw_data.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers', 'NPOINTS'])

    # Filter out unplayed weeks (points = 0)
    gw_data = gw_data[gw_data['Points'] > 0]

    if gw_data.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers', 'NPOINTS'])

    # Select relevant columns
    if 'Transfer_Cost' in gw_data.columns:
        ranking_data = gw_data[['Manager', 'Team', 'Points', 'Transfers', 'Transfer_Cost']].copy()
    else:
        ranking_data = gw_data[['Manager', 'Team', 'Points', 'Transfers']].copy()
        ranking_data['Transfer_Cost'] = 0

    # Format Transfers column: transfers(-cost)
    def format_transfer(row):
        transfers = int(row['Transfers'])
        cost = int(row['Transfer_Cost'])
        if transfers == 0:
            return "-"
        elif cost == 0:
            return str(transfers)
        else:
            return f"{transfers}(-{cost})"

    ranking_data['Transfers'] = ranking_data.apply(format_transfer, axis=1)

    # Add NPOINTS column: Points - Transfer_Cost
    ranking_data['NPOINTS'] = ranking_data['Points'] - ranking_data['Transfer_Cost']

    # Remove Transfer_Cost column
    ranking_data = ranking_data.drop(columns=['Transfer_Cost'])

    # Create ranking table
    ranked_df = create_ranking_table(ranking_data, 'NPOINTS')

    return ranked_df


def build_monthly_ranking(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int], selected_month: int) -> pd.DataFrame:
    """
    Build monthly ranking for selected month

    Args:
        gw_points_df: GW points DataFrame
        month_mapping: Dict mapping GW to month
        selected_month: Selected month number

    Returns:
        DataFrame with monthly ranking
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers', 'NPOINTS'])

    # Filter GWs for selected month
    month_gws = [gw for gw, month in month_mapping.items() if month == selected_month]

    if not month_gws:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers', 'NPOINTS'])

    # Filter data for selected month GWs
    month_data = gw_points_df[gw_points_df['GW'].isin(month_gws)].copy()

    if month_data.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Points', 'Transfers', 'NPOINTS'])

    # Group by team and sum points, transfers, and transfer costs
    agg_dict = {
        'Points': 'sum',
        'Transfers': 'sum'
    }

    if 'Transfer_Cost' in month_data.columns:
        agg_dict['Transfer_Cost'] = 'sum'

    monthly_summary = month_data.groupby(['Team_ID', 'Manager', 'Team']).agg(agg_dict).reset_index()

    if 'Transfer_Cost' not in monthly_summary.columns:
        monthly_summary['Transfer_Cost'] = 0

    # Format Transfers column
    def format_monthly_transfer(row):
        transfers = int(row['Transfers'])
        cost = int(row['Transfer_Cost'])
        if transfers == 0:
            return "-"
        elif cost == 0:
            return str(transfers)
        else:
            return f"{transfers}(-{cost})"

    monthly_summary['Transfers'] = monthly_summary.apply(format_monthly_transfer, axis=1)

    # Add NPOINTS column: Points - Transfer_Cost
    monthly_summary['NPOINTS'] = monthly_summary['Points'] - monthly_summary['Transfer_Cost']

    # Select relevant columns for ranking
    ranking_data = monthly_summary[['Manager', 'Team', 'Points', 'Transfers', 'NPOINTS']].copy()

    # Create ranking table
    ranked_df = create_ranking_table(ranking_data, 'NPOINTS')

    return ranked_df


def build_awards_summary_table(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int]) -> pd.DataFrame:
    """
    Build awards summary table showing GW, Weekly Winner, and Monthly Winner

    Args:
        gw_points_df: GW points DataFrame
        month_mapping: Dict mapping GW to month

    Returns:
        DataFrame with columns [GW, Weekly_Winner, Month, Monthly_Winner]
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['GW', 'Weekly_Winner', 'Month', 'Monthly_Winner'])

    # Get available GWs that have data
    available_gws = sorted(gw_points_df['GW'].unique())

    results = []
    for gw in available_gws:
        weekly_winner = "-"
        weekly_ranking = build_weekly_ranking(gw_points_df, gw)

        if not weekly_ranking.empty:
            # Get all tied winners (rank 1)
            winners = weekly_ranking[weekly_ranking['Rank'] == 1]
            if len(winners) > 0:
                if len(winners) == 1:
                    weekly_winner = winners.iloc[0]['Manager']
                else:
                    # Multiple tied winners - join with " & "
                    winner_names = winners['Manager'].tolist()
                    weekly_winner = " & ".join(winner_names)

        # Get month for this GW
        month = month_mapping.get(gw, 1)

        results.append({
            'GW': gw,
            'Weekly_Winner': weekly_winner,
            'Month': month
        })

    awards_summary_df = pd.DataFrame(results)

    # Calculate monthly winners
    monthly_winners = {}
    available_months = sorted(set(month_mapping.values()))

    for month in available_months:
        monthly_ranking = build_monthly_ranking(gw_points_df, month_mapping, month)
        if not monthly_ranking.empty:
            # Get all tied winners (rank 1)
            winners = monthly_ranking[monthly_ranking['Rank'] == 1]
            if len(winners) > 0:
                if len(winners) == 1:
                    monthly_winners[month] = winners.iloc[0]['Manager']
                else:
                    winner_names = winners['Manager'].tolist()
                    monthly_winners[month] = " & ".join(winner_names)

    # Add monthly winners
    awards_summary_df['Monthly_Winner'] = awards_summary_df['Month'].map(monthly_winners).fillna("")

    return awards_summary_df


def build_awards_leaderboard(gw_points_df: pd.DataFrame, month_mapping: Dict[int, int], current_gw: int = 38) -> pd.DataFrame:
    """
    Build awards leaderboard with rankings, wins count, and prize money

    Args:
        gw_points_df: GW points DataFrame
        month_mapping: Dict mapping GW to month
        current_gw: Current gameweek (to determine completed months)

    Returns:
        DataFrame with awards leaderboard
    """
    if gw_points_df.empty:
        return pd.DataFrame(columns=['Medal', 'Rank', 'Manager', 'Team', 'Weekly_Wins', 'Monthly_Wins', 'Total_Awards', 'Prize_Money'])

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
            'Monthly_Wins': 0,
            'Weekly_Prize_Money': 0.0,
            'Monthly_Prize_Money': 0.0
        })

    awards_df = pd.DataFrame(awards_data)

    # Prize money constants
    WEEKLY_PRIZE = 300000
    MONTHLY_PRIZE = 500000

    # Calculate weekly wins - only for GWs that have been played
    available_gws = sorted([gw for gw in gw_points_df['GW'].unique() if gw <= current_gw])

    for gw in available_gws:
        weekly_ranking = build_weekly_ranking(gw_points_df, gw)
        if not weekly_ranking.empty:
            winners = weekly_ranking[weekly_ranking['Rank'] == 1]
            num_winners = len(winners)
            if num_winners > 0:
                prize_per_winner = WEEKLY_PRIZE / num_winners
                for _, winner in winners.iterrows():
                    manager_name = winner['Manager']
                    awards_df.loc[awards_df['Manager'] == manager_name, 'Weekly_Wins'] += 1
                    awards_df.loc[awards_df['Manager'] == manager_name, 'Weekly_Prize_Money'] += prize_per_winner

    # Build reverse mapping: month -> [gw_start, gw_end]
    month_ranges = {}
    for gw, month in month_mapping.items():
        if month not in month_ranges:
            month_ranges[month] = [gw, gw]
        else:
            month_ranges[month][0] = min(month_ranges[month][0], gw)
            month_ranges[month][1] = max(month_ranges[month][1], gw)

    # Calculate monthly wins - only for completed months
    available_months = sorted(set(month_mapping.values()))

    for month in available_months:
        # Only count if month is complete (current_gw >= last GW of month)
        if month in month_ranges and current_gw >= month_ranges[month][1]:
            monthly_ranking = build_monthly_ranking(gw_points_df, month_mapping, month)
            if not monthly_ranking.empty:
                winners = monthly_ranking[monthly_ranking['Rank'] == 1]
                num_winners = len(winners)
                if num_winners > 0:
                    prize_per_winner = MONTHLY_PRIZE / num_winners
                    for _, winner in winners.iterrows():
                        manager_name = winner['Manager']
                        awards_df.loc[awards_df['Manager'] == manager_name, 'Monthly_Wins'] += 1
                        awards_df.loc[awards_df['Manager'] == manager_name, 'Monthly_Prize_Money'] += prize_per_winner

    # Calculate totals
    awards_df['Total_Awards'] = awards_df['Weekly_Wins'] + awards_df['Monthly_Wins']
    awards_df['Total_Prize_Money'] = awards_df['Weekly_Prize_Money'] + awards_df['Monthly_Prize_Money']

    # Sort by total prize money
    awards_df = awards_df.sort_values(
        ['Total_Prize_Money', 'Total_Awards', 'Weekly_Wins', 'Monthly_Wins'],
        ascending=[False, False, False, False]
    ).reset_index(drop=True)

    # Add rank
    awards_df['Rank'] = range(1, len(awards_df) + 1)

    # Add medal
    def get_award_medal(rank):
        if rank == 1:
            return "🏆"
        elif rank == 2:
            return "🥈"
        elif rank == 3:
            return "🥉"
        return ""

    awards_df['Medal'] = awards_df['Rank'].apply(get_award_medal)

    # Add emotion icon
    def get_emotion_icon(prize_money):
        if prize_money >= 1000000:
            return "😄"
        elif prize_money > 0:
            return "😢"
        return "😭"

    awards_df['Emotion'] = awards_df['Total_Prize_Money'].apply(get_emotion_icon)
    awards_df['Manager_Display'] = awards_df['Manager'] + ' ' + awards_df['Emotion']

    # Format prize money
    def format_prize_money(amount):
        if amount >= 1000000:
            return f"₫{amount/1000000:.1f}M"
        elif amount >= 1000:
            return f"₫{amount/1000:.0f}K"
        return f"₫{amount:.0f}"

    awards_df['Prize_Money'] = awards_df['Total_Prize_Money'].apply(format_prize_money)

    # Select columns
    result = awards_df[['Medal', 'Rank', 'Manager_Display', 'Team', 'Weekly_Wins', 'Monthly_Wins', 'Total_Awards', 'Prize_Money']].copy()
    result = result.rename(columns={'Manager_Display': 'Manager'})

    return result


def build_fun_stats_table(entries_df: pd.DataFrame, gw_range: List[int], bootstrap_df: pd.DataFrame,
                         max_entries: Optional[int] = None, progress_callback=None) -> pd.DataFrame:
    """
    Build fun statistics table showing best/worst captains, best bench, and best/worst transfers for each GW
    """
    if max_entries:
        entries_df = entries_df.head(max_entries)

    results = []
    completed_gws = [gw for gw in gw_range if gw <= max(gw_range)]
    total_requests = len(entries_df)

    # Create player name mapping
    player_mapping = dict(zip(bootstrap_df['id'], bootstrap_df['web_name']))

    # Get history data for all entries (for bench points)
    history_data = {}
    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
        future_to_entry = {}
        for _, entry in entries_df.iterrows():
            future = executor.submit(get_entry_history, entry['Team_ID'])
            future_to_entry[future] = entry['Team_ID']

        completed = 0
        for future in as_completed(future_to_entry):
            entry_id = future_to_entry[future]
            completed += 1
            if progress_callback:
                progress_callback(completed, total_requests, f"Fetching history: {completed}/{total_requests}")
            try:
                data = future.result()
                if data:
                    history_data[entry_id] = data
            except:
                history_data[entry_id] = None
            time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)

    # Process each GW
    for gw_idx, gw in enumerate(completed_gws):
        if progress_callback:
            progress_callback(gw_idx, len(completed_gws), f"Processing GW {gw}...")

        gw_data = []
        with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as executor:
            future_to_info = {}
            for _, entry in entries_df.iterrows():
                future = executor.submit(get_entry_gw_picks, entry['Team_ID'], gw)
                future_to_info[future] = (entry['Team_ID'], entry['Manager'], entry['Team'])

            for future in as_completed(future_to_info):
                team_id, manager, team = future_to_info[future]
                try:
                    data = future.result()

                    # Get bench points from history
                    bench_total_points = 0
                    if team_id in history_data and history_data[team_id]:
                        for event in history_data[team_id].get('current', []):
                            if event.get('event') == gw:
                                bench_total_points = event.get('points_on_bench', 0)
                                break

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
                            captain_points *= captain_pick.get('multiplier', 1)

                        # Get transfer data
                        transfer_diff = None
                        try:
                            transfer_data = get_entry_transfers(team_id)
                            if transfer_data and isinstance(transfer_data, list):
                                gw_transfers = [t for t in transfer_data if t.get('event') == gw]
                                if gw_transfers:
                                    total_in_points = 0
                                    total_out_points = 0
                                    for transfer in gw_transfers:
                                        element_in = transfer.get('element_in')
                                        element_out = transfer.get('element_out')
                                        if element_in:
                                            total_in_points += get_player_gw_points(element_in, gw)
                                        if element_out:
                                            total_out_points += get_player_gw_points(element_out, gw)
                                    transfer_diff = total_in_points - total_out_points
                        except:
                            transfer_diff = None

                        gw_data.append({
                            'team_id': team_id, 'manager': manager, 'team': team,
                            'captain_name': captain_name, 'captain_points': captain_points,
                            'bench_total_points': bench_total_points, 'transfer_diff': transfer_diff
                        })
                except:
                    gw_data.append({
                        'team_id': team_id, 'manager': manager, 'team': team,
                        'captain_name': "Unknown", 'captain_points': 0,
                        'bench_total_points': 0, 'transfer_diff': None
                    })
                time.sleep(config.REQUEST_DELAY / config.MAX_WORKERS)

        # Process GW results
        if gw_data:
            max_captain = max(gw_data, key=lambda x: x['captain_points'])['captain_points']
            min_captain = min(gw_data, key=lambda x: x['captain_points'])['captain_points']
            max_bench = max(gw_data, key=lambda x: x['bench_total_points'])['bench_total_points']

            transfer_data = [x for x in gw_data if x['transfer_diff'] is not None]
            max_transfer = max(transfer_data, key=lambda x: x['transfer_diff'])['transfer_diff'] if transfer_data else None
            min_transfer = min(transfer_data, key=lambda x: x['transfer_diff'])['transfer_diff'] if transfer_data else None

            best_captains = [x for x in gw_data if x['captain_points'] == max_captain]
            worst_captains = [x for x in gw_data if x['captain_points'] == min_captain]
            best_benches = [x for x in gw_data if x['bench_total_points'] == max_bench]
            best_transfers = [x for x in transfer_data if x['transfer_diff'] == max_transfer] if max_transfer is not None else []
            worst_transfers = [x for x in transfer_data if x['transfer_diff'] == min_transfer] if min_transfer is not None else []

            def format_transfer(diff):
                if diff > 0: return f"+{diff}"
                return str(diff)

            results.append({
                'GW': gw,
                'Best_Captain': " | ".join([f"{x['manager']} - {x['captain_name']} ({x['captain_points']})" for x in best_captains]),
                'Worst_Captain': " | ".join([f"{x['manager']} - {x['captain_name']} ({x['captain_points']})" for x in worst_captains]),
                'Best_Bench': " | ".join([f"{x['manager']} ({x['bench_total_points']})" for x in best_benches]),
                'Best_Transfer': " | ".join([f"{x['manager']} ({format_transfer(x['transfer_diff'])})" for x in best_transfers]) if best_transfers else "-",
                'Worst_Transfer': " | ".join([f"{x['manager']} ({format_transfer(x['transfer_diff'])})" for x in worst_transfers]) if worst_transfers else "-"
            })

    if not results:
        raise FPLError("Unable to fetch fun statistics data")

    return pd.DataFrame(results)
