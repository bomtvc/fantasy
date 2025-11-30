import sys
sys.path.insert(0, '.')

from services.fpl_api import get_current_gw

print("Testing updated get_current_gw() function...")
print("=" * 60)

current_gw = get_current_gw()

print(f"✅ Current GW detected: GW{current_gw}")
print("=" * 60)

# Parse month mapping
mapping_str = '1-4,5-8,9-12,13-16,17-20,21-24,25-28,29-32,33-36,37-38'
month_mapping = {}
for idx, month_range in enumerate(mapping_str.split(','), 1):
    start, end = map(int, month_range.split('-'))
    for gw in range(start, end + 1):
        month_mapping[gw] = idx

current_month = month_mapping.get(current_gw, 0)
month_gws = [gw for gw, month in month_mapping.items() if month == current_month]

print(f"\n📅 Current Month: Month {current_month}")
print(f"📊 Month Range: GW{min(month_gws)} - GW{max(month_gws)}")
print(f"\nExpected: GW13, Month 4 (GW13-16)")
