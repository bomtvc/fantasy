import requests

# Test fixtures API directly
for gw in [13, 12]:
    try:
        url = f"https://fantasy.premierleague.com/api/fixtures/?event={gw}"
        response = requests.get(url, timeout=10)
        fixtures = response.json()
       
        started_count = sum(1 for f in fixtures if f.get('started', False))
        finished_count = sum(1 for f in fixtures if f.get('finished', False))
        
        print(f"\nGW{gw}:")
        print(f"  Total fixtures: {len(fixtures)}")
        print(f"  Started: {started_count}")
        print(f"  Finished: {finished_count}")
        
        if started_count > 0:
            print(f"  ✅ This is the current GW (has started fixtures)")
    except Exception as e:
        print(f"\nGW{gw}: Error - {e}")
