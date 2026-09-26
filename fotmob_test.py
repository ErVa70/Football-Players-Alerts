import requests
from datetime import datetime, timezone

today = datetime.now(timezone.utc).strftime("%Y%m%d")

url = "https://www.fotmob.com/api/data/matches"

params = {
    "date": today
}

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(
    url,
    params=params,
    headers=headers,
    timeout=20
)

response.raise_for_status()

data = response.json()

print("FotMob responded successfully! ✅")
print()

leagues = data.get("leagues", [])

for league in leagues:
    matches = league.get("matches", [])

    for match in matches[:5]:
        match_id = match.get("id")
        home = match.get("home", {}).get("name", "Unknown")
        away = match.get("away", {}).get("name", "Unknown")

        print(f"🏆 {league.get('name')}")
        print(f"   {home} vs {away}")
        print(f"   Match ID: {match_id}")
        print()
