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

response.raise_for_status()

data = response.json()

print("FotMob match details received! ✅")
print()

# --------------------------------------------------
# BASIC MATCH INFORMATION
# --------------------------------------------------

general = data.get("general", {})
header = data.get("header", {})

print("========== MATCH ==========")
print(general.get("matchName"))
print()

print("========== SCORE ==========")

for team in header.get("teams", []):
    print(
        f"{team.get('name')}: {team.get('score')}"
    )

print()

# --------------------------------------------------
# LINEUPS
# --------------------------------------------------

print("========== LINEUPS ==========")

lineup = data.get("content", {}).get("lineup", {})

for team_key in ["homeTeam", "awayTeam"]:

    team = lineup.get(team_key, {})

    if not team:
        continue

    print()
    print(team.get("name"))

    print("  Starters:")

    for player in team.get("starters", []):
        print(
            f"    {player.get('name')}"
        )

    print("  Substitutes:")

    for player in team.get("subs", []):
        print(
            f"    {player.get('name')}"
        )

print()

# --------------------------------------------------
# MATCH EVENTS
# --------------------------------------------------

print("========== EVENTS ==========")

match_facts = data.get("content", {}).get("matchFacts", {})

events = match_facts.get("events", {}).get("events", [])

for event in events:

    event_type = event.get("type")
    time = event.get("timeStr")
    player = event.get("player", {}).get("name")

    print(
        f"{time}' | {event_type} | {player}"
    )
