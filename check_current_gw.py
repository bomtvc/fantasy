import requests

# Get current GW from FPL API
data = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/').json()
events = data.get('events', [])

# Find current GW (latest finished or current)
finished_gw = max([e['id'] for e in events if e.get('finished', False)], default=0)
current_gw = finished_gw if finished_gw > 0 else next((e['id'] for e in events if e.get('is_current', False)), 1)

# Month mapping from config
mapping_str = '1-4,5-8,9-12,13-16,17-20,21-24,25-28,29-32,33-36,37-38'

# Parse month mapping
month_mapping = {}
for idx, month_range in enumerate(mapping_str.split(','), 1):
    start, end = map(int, month_range.split('-'))
    for gw in range(start, end + 1):
        month_mapping[gw] = idx

# Get current month
current_month = month_mapping.get(current_gw, 0)

# Get month range
month_gws = [gw for gw, month in month_mapping.items() if month == current_month]
month_start = min(month_gws)
month_end = max(month_gws)

print(f"🎯 Current Gameweek: GW{current_gw}")
print(f"📅 Current Month: Month {current_month}")
print(f"📊 Month Range: GW{month_start} - GW{month_end}")
print(f"\n월별 매핑:")
for idx, month_range in enumerate(mapping_str.split(','), 1):
    start, end = month_range.split('-')
    status = "✓ CURRENT" if idx == current_month else ""
    print(f"  Month {idx}: GW{start}-{end} {status}")
