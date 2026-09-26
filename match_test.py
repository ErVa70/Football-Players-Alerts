import requests
import json

MATCH_ID = 5181850

# --------------------------------------------------
# LOAD FOLLOWED PLAYERS
# --------------------------------------------------

with open("players.json", "r", encoding="utf-8") as file:
    player_data = json.load(file)

followed_players = player_data["players"]

print("========== FOLLOWED PLAYERS ==========")

for player in followed_players:
    print(f"👤 {player}")

print()

# --------------------------------------------------
# GET MATCH DETAILS
# --------------------------------------------------

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

print("========== MATCH ==========")
print(general.get("matchName"))
print()

# --------------------------------------------------
# FIND FOLLOWED PLAYERS
# --------------------------------------------------

lineup = data.get("content", {}).get("lineup", {})

found_players = []

for team_key in ["homeTeam", "awayTeam"]:

    team = lineup.get(team_key, {})

    if not team:
        continue

    team_name = team.get("name")

    # Check starters
    for player in team.get("starters", []):

        player_name = player.get("name")

        if player_name in followed_players:

            found_players.append(player_name)

            print(
                f"✅ {player_name} is starting for {team_name}"
            )

    # Check substitutes
    for player in team.get("subs", []):

        player_name = player.get("name")

        if player_name in followed_players:

            found_players.append(player_name)

            print(
                f"🪑 {player_name} is on the bench for {team_name}"
            )

print()

# --------------------------------------------------
# SUMMARY
# --------------------------------------------------

print("========== RESULT ==========")

if found_players:

    print("We found your followed player(s)! 🎉")

    for player in found_players:
        print(f"→ {player}")

else:

    print("None of your followed players are in this match.")
