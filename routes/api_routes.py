"""
API Routes
RESTful API endpoints for AJAX calls
"""

from flask import jsonify, request, session, send_file
from . import api_bp
from extensions import cache
import config
from services import (
    get_bootstrap_static,
    get_current_gw,
    get_all_league_entries,
    build_gw_points_table,
    build_month_points_table_full,
    build_transfer_history_table,
    build_chip_history_table,
    parse_month_mapping,
    calculate_awards_statistics,
    build_weekly_ranking,
    build_monthly_ranking,
    build_awards_summary_table,
    build_awards_leaderboard,
    build_fun_stats_table
)
import pandas as pd
import io


@api_bp.route('/current-gw')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL)  # 15 minutes
def get_current_gw_endpoint():
    """Get current gameweek from FPL API"""
    try:
        current_gw = get_current_gw()
        return jsonify({
            'success': True,
            'current_gw': current_gw
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'current_gw': 1  # Fallback
        }), 500


@api_bp.route('/league/<int:league_id>')
@cache.cached(timeout=config.LEAGUE_CACHE_TTL, query_string=True)  # 1 hour - semi-static
def get_league(league_id):
    """Get league basic information including leader and current GW"""
    try:
        phase = request.args.get('phase', 1, type=int)
        entries_df = get_all_league_entries(league_id, phase)

        # Get current gameweek
        current_gw = get_current_gw()

        # Get league leader (manager with highest total points)
        league_leader = '-'
        leader_points = 0
        if not entries_df.empty and 'Total' in entries_df.columns:
            max_idx = entries_df['Total'].idxmax()
            league_leader = entries_df.loc[max_idx, 'Manager']
            leader_points = int(entries_df.loc[max_idx, 'Total'])

        # Get best GW points (highest single GW score in the league)
        best_gw_points = 0
        best_gw_manager = '-'
        try:
            gw_range = list(range(1, current_gw + 1))
            gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries=None)
            if not gw_points_df.empty and 'Points' in gw_points_df.columns:
                max_idx = gw_points_df['Points'].idxmax()
                best_gw_points = int(gw_points_df.loc[max_idx, 'Points'])
                best_gw_manager = gw_points_df.loc[max_idx, 'Manager']
        except Exception as e:
            print(f"Warning: Could not get best GW points: {e}")

        return jsonify({
            'success': True,
            'data': {
                'total_entries': len(entries_df),
                'league_id': league_id,
                'phase': phase,
                'current_gw': current_gw,
                'league_leader': league_leader,
                'leader_points': leader_points,
                'best_gw_points': best_gw_points,
                'best_gw_manager': best_gw_manager
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/league/<int:league_id>/entries')
@cache.cached(timeout=config.LEAGUE_CACHE_TTL, query_string=True)  # 1 hour - semi-static
def get_league_entries_api(league_id):
    """Get all league entries with awards statistics"""
    try:
        phase = request.args.get('phase', 1, type=int)
        max_entries = request.args.get('max_entries', type=int)
        month_mapping_str = request.args.get('month_mapping', config.DEFAULT_MONTH_MAPPING)

        entries_df = get_all_league_entries(league_id, phase)

        if max_entries:
            entries_df = entries_df.head(max_entries)

        # Calculate awards statistics
        try:
            current_gw = get_current_gw()
            gw_range = list(range(1, current_gw + 1))
            gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries=None)
            month_mapping = parse_month_mapping(month_mapping_str)
            awards_df = calculate_awards_statistics(gw_points_df, month_mapping)

            # Merge awards with entries
            entries_df = entries_df.merge(
                awards_df[['Team_ID', 'Weekly_Wins', 'Monthly_Wins', 'Total_Prize_Money']],
                on='Team_ID',
                how='left'
            )
            entries_df['Weekly_Wins'] = entries_df['Weekly_Wins'].fillna(0).astype(int)
            entries_df['Monthly_Wins'] = entries_df['Monthly_Wins'].fillna(0).astype(int)
            entries_df['Total_Prize_Money'] = entries_df['Total_Prize_Money'].fillna(0).astype(int)
        except Exception as e:
            print(f"Warning: Could not calculate awards: {e}")
            entries_df['Weekly_Wins'] = 0
            entries_df['Monthly_Wins'] = 0
            entries_df['Total_Prize_Money'] = 0

        return jsonify({
            'success': True,
            'data': entries_df.to_dict('records')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/gw-points')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL, query_string=True)  # 15 minutes - dynamic
def get_gw_points():
    """Get GW points table"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 10, type=int)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Build GW points table
        gw_range = list(range(gw_start, gw_end + 1))
        gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries)

        # Ensure GW column is integer type to avoid comparison errors
        gw_points_df['GW'] = gw_points_df['GW'].astype(int)

        # Pivot for display
        display_df = gw_points_df.pivot_table(
            index=['Manager', 'Team', 'Team_ID'],
            columns='GW',
            values='Points',
            fill_value=0
        ).reset_index()

        # Convert column names to strings to avoid type comparison errors in JavaScript
        # (pivot_table creates integer column names from GW values)
        display_df.columns = [str(col) if isinstance(col, int) else col for col in display_df.columns]

        # Ensure all numeric values are Python native types (not numpy types)
        for col in display_df.columns:
            if display_df[col].dtype in ['int64', 'float64']:
                display_df[col] = display_df[col].astype(int)

        return jsonify({
            'success': True,
            'data': display_df.to_dict('records'),
            'columns': display_df.columns.tolist()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/month-points')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL, query_string=True)  # 15 minutes - dynamic
def get_month_points():
    """Get month points table"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 10, type=int)
        month_mapping_str = request.args.get('month_mapping', '1-4,5-9,10-13,14-17,18-21,22-26,27-30,31-34,35-38')
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        # Parse month mapping
        month_mapping = parse_month_mapping(month_mapping_str)

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Build GW points table first
        gw_range = list(range(gw_start, gw_end + 1))
        gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries)

        # Build month points table
        month_df = build_month_points_table_full(gw_points_df, month_mapping)

        return jsonify({
            'success': True,
            'data': month_df.to_dict('records'),
            'columns': month_df.columns.tolist()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/chip-history')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL, query_string=True)  # 15 minutes - dynamic
def get_chip_history_api():
    """Get chip history"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 10, type=int)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Build chip history table
        gw_range = list(range(gw_start, gw_end + 1))
        chip_df = build_chip_history_table(entries_df, gw_range, max_entries)

        # Pivot for display
        display_df = chip_df.pivot_table(
            index=['Manager', 'Team'],
            columns='GW',
            values='Active_Chip',
            aggfunc='first',
            fill_value='-'
        ).reset_index()

        # Rename GW columns to strings (e.g., 1 -> "GW1")
        new_columns = {}
        for col in display_df.columns:
            if isinstance(col, int):
                new_columns[col] = f'GW{col}'
        display_df = display_df.rename(columns=new_columns)

        # Convert columns to list of strings
        columns = [str(col) for col in display_df.columns.tolist()]

        return jsonify({
            'success': True,
            'data': display_df.to_dict('records'),
            'columns': columns
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/weekly-ranking')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL, query_string=True)  # 15 minutes - dynamic
def get_weekly_ranking():
    """Get weekly ranking for a specific GW"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        gw = request.args.get('gw', type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 38, type=int)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        if not gw:
            return jsonify({'success': False, 'error': 'gw required'}), 400

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Build GW points table
        gw_range = list(range(gw_start, gw_end + 1))
        gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries)

        # Build weekly ranking
        ranking_df = build_weekly_ranking(gw_points_df, gw)

        return jsonify({
            'success': True,
            'data': ranking_df.to_dict('records'),
            'columns': ranking_df.columns.tolist()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/monthly-ranking')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL, query_string=True)  # 15 minutes - dynamic
def get_monthly_ranking():
    """Get monthly ranking for a specific month"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        month = request.args.get('month', type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 38, type=int)
        month_mapping_str = request.args.get('month_mapping', config.DEFAULT_MONTH_MAPPING)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        if not month:
            return jsonify({'success': False, 'error': 'month required'}), 400

        # Parse month mapping
        month_mapping = parse_month_mapping(month_mapping_str)

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Build GW points table
        gw_range = list(range(gw_start, gw_end + 1))
        gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries)

        # Build monthly ranking
        ranking_df = build_monthly_ranking(gw_points_df, month_mapping, month)

        return jsonify({
            'success': True,
            'data': ranking_df.to_dict('records'),
            'columns': ranking_df.columns.tolist()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/awards-summary')
@cache.cached(timeout=config.API_CACHE_TTL, query_string=True)  # 5 minutes - calculated data
def get_awards_summary():
    """Get awards summary table (weekly and monthly winners)"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 38, type=int)
        month_mapping_str = request.args.get('month_mapping', config.DEFAULT_MONTH_MAPPING)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        # Parse month mapping
        month_mapping = parse_month_mapping(month_mapping_str)

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Build GW points table
        gw_range = list(range(gw_start, gw_end + 1))
        gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries)

        # Build awards summary
        summary_df = build_awards_summary_table(gw_points_df, month_mapping)

        return jsonify({
            'success': True,
            'data': summary_df.to_dict('records'),
            'columns': summary_df.columns.tolist()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/awards-leaderboard')
@cache.cached(timeout=config.API_CACHE_TTL, query_string=True)  # 5 minutes - calculated data
def get_awards_leaderboard():
    """Get awards leaderboard"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 38, type=int)
        month_mapping_str = request.args.get('month_mapping', config.DEFAULT_MONTH_MAPPING)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        # Parse month mapping
        month_mapping = parse_month_mapping(month_mapping_str)

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Build GW points table
        gw_range = list(range(gw_start, gw_end + 1))
        gw_points_df = build_gw_points_table(entries_df, gw_range, max_entries)

        # Build awards leaderboard
        leaderboard_df = build_awards_leaderboard(gw_points_df, month_mapping)

        return jsonify({
            'success': True,
            'data': leaderboard_df.to_dict('records'),
            'columns': leaderboard_df.columns.tolist()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/export/csv', methods=['POST'])
def export_csv():
    """Export data to CSV"""
    try:
        data = request.json.get('data', [])
        filename = request.json.get('filename', 'export.csv')

        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        # Convert to DataFrame
        df = pd.DataFrame(data)

        # Create CSV in memory
        output = io.StringIO()
        df.to_csv(output, index=False, encoding='utf-8')
        output.seek(0)

        # Convert to bytes
        mem = io.BytesIO()
        mem.write(output.getvalue().encode('utf-8'))
        mem.seek(0)

        return send_file(
            mem,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/cache/clear', methods=['POST'])
def clear_cache():
    """Clear application cache"""
    try:
        # Clear all cache (both Flask-Caching and file system)
        cache.clear()

        # Also clear cache directory files if exists
        import os
        import glob
        cache_dir = config.CACHE_DIR
        if os.path.exists(cache_dir):
            cache_files = glob.glob(os.path.join(cache_dir, '*'))
            for f in cache_files:
                try:
                    os.remove(f)
                except:
                    pass

        return jsonify({
            'success': True,
            'message': 'All cache cleared successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/cache/stats', methods=['GET'])
def get_cache_stats():
    """Get cache statistics"""
    try:
        import os
        import glob
        
        cache_dir = config.CACHE_DIR
        cache_files = glob.glob(os.path.join(cache_dir, '*'))
        
        total_files = len(cache_files)
        total_size = sum(os.path.getsize(f) for f in cache_files if os.path.isfile(f))
        
        # Convert size to human-readable format
        if total_size < 1024:
            size_str = f"{total_size} B"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.2f} KB"
        else:
            size_str = f"{total_size / (1024 * 1024):.2f} MB"
        
        return jsonify({
            'success': True,
            'stats': {
                'cache_type': config.CACHE_TYPE,
                'cache_dir': cache_dir,
                'total_files': total_files,
                'total_size': total_size,
                'total_size_human': size_str,
                'cache_threshold': config.CACHE_THRESHOLD,
                'ttl_config': {
                    'bootstrap': f"{config.BOOTSTRAP_CACHE_TTL}s ({config.BOOTSTRAP_CACHE_TTL // 3600}h)",
                    'league': f"{config.LEAGUE_CACHE_TTL}s ({config.LEAGUE_CACHE_TTL // 60}min)",
                    'gw_data': f"{config.GW_DATA_CACHE_TTL}s ({config.GW_DATA_CACHE_TTL // 60}min)",
                    'api_default': f"{config.API_CACHE_TTL}s ({config.API_CACHE_TTL // 60}min)"
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/fun-stats')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL, query_string=True)  # 15 minutes - dynamic
def get_fun_stats_api():
    """Get fun statistics"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        gw_start = request.args.get('gw_start', 1, type=int)
        gw_end = request.args.get('gw_end', 10, type=int)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        # Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Get bootstrap data for player names
        bootstrap_df = get_bootstrap_static()

        # Build fun stats table
        gw_range = list(range(gw_start, gw_end + 1))
        fun_stats_df = build_fun_stats_table(entries_df, gw_range, bootstrap_df, max_entries)

        return jsonify({
            'success': True,
            'data': fun_stats_df.to_dict('records'),
            'columns': fun_stats_df.columns.tolist()
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/transfer-history')
@cache.cached(timeout=config.GW_DATA_CACHE_TTL, query_string=True)  # 15 minutes - dynamic
def get_transfer_history_api():
    """Get transfer history for all managers by GW"""
    try:
        league_id = request.args.get('league_id', type=int)
        phase = request.args.get('phase', 1, type=int)
        max_entries = request.args.get('max_entries', type=int)

        if not league_id:
            return jsonify({'success': False, 'error': 'league_id required'}), 400

        #Get league entries
        entries_df = get_all_league_entries(league_id, phase)

        # Get bootstrap data for player names
        bootstrap_df = get_bootstrap_static()

        # Build transfer history table
        transfer_df = build_transfer_history_table(entries_df, bootstrap_df, max_entries)

        if transfer_df.empty:
            return jsonify({
                'success': True,
                'data': [],
                'columns': ['Manager', 'Team'],
                'pivot_data': []
            })

        # Group transfers by Manager, Team, GW
        grouped_transfers = transfer_df.groupby(['Manager', 'Team', 'GW'])['Transfer'].apply(
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
        transfer_pivot = transfer_pivot.reset_index()
        transfer_pivot = transfer_pivot.sort_values('Manager')

        # Get available GWs
        available_gws = sorted([int(col.replace('GW', '')) for col in transfer_pivot.columns if col.startswith('GW')])
        gw_cols = ['Manager', 'Team'] + [f'GW{gw}' for gw in available_gws]
        transfer_pivot = transfer_pivot[gw_cols]

        # Calculate statistics
        stats = {
            'total_transfers': len(transfer_df),
            'transfers_by_gw': transfer_df.groupby('GW').size().to_dict(),
            'transfers_by_manager': transfer_df.groupby('Manager').size().to_dict(),
            'most_transferred_in': transfer_df['Player_In'].value_counts().head(5).to_dict(),
            'most_transferred_out': transfer_df['Player_Out'].value_counts().head(5).to_dict()
        }

        return jsonify({
            'success': True,
            'data': transfer_pivot.to_dict('records'),
            'columns': transfer_pivot.columns.tolist(),
            'raw_data': transfer_df.to_dict('records'),
            'stats': stats
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500