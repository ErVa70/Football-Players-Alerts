import requests
from datetime import datetime, timezone

# Get today's date in UTC
today = datetime.now(timezone.utc).strftime("%Y%m%d")

url = "https://www.fotmob.com/api/data/matches"

params = {
    "date": today
}

headers = {
    "User-Agent": "Mozilla/5.0"
}

print(f"Checking FotMob for matches on {today}...")
print()

response = requests.get(
    url,
    params=params,
    headers=headers,
    timeout=20
)

print("HTTP status:", response.status_code)
print("Content-Type:", response.headers.get("Content-Type"))
print()

response.raise_for_status()

data = response.json()

print("FotMob responded successfully! ✅")
print()

leagues = data.get("leagues", [])

print(f"Number of leagues returned: {len(leagues)}")
print()

for league in leagues[:5]:
    print(f"🏆 {league.get('name')}")

    matches = league.get("matches", [])

    for match in matches[:3]:
        home = match.get("home", {}).get("name", "Unknown")
        away = match.get("away", {}).get("name", "Unknown")

        print(f"   {home} vs {away}")

    print()
