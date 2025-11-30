import requests

# Check GW13 status
gw13_fixtures = requests.get('https://fantasy.premierleague.com/api/fixtures/?event=13').json()
gw12_fixtures = requests.get('https://fantasy.premierleague.com/api/fixtures/?event=12').json()

# Get bootstrap data
bootstrap = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/').json()
events = bootstrap.get('events', [])

print("=" * 60)
print("CHECKING GAMEWEEK STATUS")
print("=" * 60)

# Check GW12
gw12_event = next((e for e in events if e['id'] == 12), None)
if gw12_event:
    print(f"\n📊 GW12 Status:")
    print(f"  - Finished: {gw12_event.get('finished', False)}")
    print(f"  - Is Current: {gw12_event.get('is_current', False)}")
    print(f"  - Deadline: {gw12_event.get('deadline_time', 'N/A')}")
    
# Check if any GW12 fixtures started
gw12_started = any(f.get('started', False) for f in gw12_fixtures)
print(f"  - Any fixtures started: {gw12_started}")

# Check GW13
gw13_event = next((e for e in events if e['id'] == 13), None)
if gw13_event:
    print(f"\n📊 GW13 Status:")
    print(f"  - Finished: {gw13_event.get('finished', False)}")
    print(f"  - Is Current: {gw13_event.get('is_current', False)}")
    print(f"  - Deadline: {gw13_event.get('deadline_time', 'N/A')}")

# Check if any GW13 fixtures started
gw13_started = any(f.get('started', False) for f in gw13_fixtures)
print(f"  - Any fixtures started: {gw13_started}")

print("\n" + "=" * 60)
print("CURRENT LOGIC RESULT")
print("=" * 60)

# Current logic (finds last finished)
finished_gw = max([e['id'] for e in events if e.get('finished', False)], default=0)
print(f"Last finished GW: {finished_gw}")

# Find current (with is_current flag)
current_by_flag = next((e['id'] for e in events if e.get('is_current', False)), None)
print(f"Current by flag: {current_by_flag}")

print("\n" + "=" * 60)
print("BETTER LOGIC (checking started fixtures)")
print("=" * 60)

# Better approach: check for started fixtures
def get_current_gw_improved():
    # Check each GW to find the one with started fixtures
    for event in sorted(events, key=lambda x: x['id'], reverse=True):
        gw_id = event['id']
        fixtures = requests.get(f'https://fantasy.premierleague.com/api/fixtures/?event={gw_id}').json()
        
        # If any fixture has started, this is the current GW
        if any(f.get('started', False) for f in fixtures):
            return gw_id
    
    # Fallback to is_current flag
    return next((e['id'] for e in events if e.get('is_current', False)), 1)

improved_gw = get_current_gw_improved()
print(f"✅ Improved detection: GW{improved_gw}")
