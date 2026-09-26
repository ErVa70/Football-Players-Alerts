import requests

MATCH_ID = 5181850

url = "https://www.fotmob.com/api/data/matchDetails"

params = {
    "matchId": MATCH_ID
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

print("HTTP status:", response.status_code)
print()

response.raise_for_status()

data = response.json()

print("FotMob match details received! ✅")
print()

# Basic match information
general = data.get("general", {})
header = data.get("header", {})

print("Match:", general.get("matchName"))
print("League:", general.get("leagueName"))
print("Started:", general.get("started"))
print("Finished:", general.get("finished"))
print()

# Score
teams = header.get("teams", [])

for team in teams:
    print(
        f"{team.get('name')}: "
        f"{team.get('score')}"
    )

print()

# Show top-level sections
print("Available data sections:")
print(list(data.keys()))
