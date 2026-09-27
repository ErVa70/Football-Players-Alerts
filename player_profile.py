import requests
import json


# --------------------------------------------------
# LOAD PLAYERS
# --------------------------------------------------

with open("players.json", "r", encoding="utf-8") as file:
    data = json.load(file)

players = data["players"]

headers = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# GET PLAYER PROFILES
# --------------------------------------------------

for player in players:

    name = player["name"]
    player_id = player["fotmob_id"]

    print("=" * 60)
    print(f"PLAYER: {name}")
    print(f"FOTMOB ID: {player_id}")
    print("=" * 60)

    url = "https://www.fotmob.com/api/data/playerData"

    response = requests.get(
        url,
        params={"id": player_id},
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    profile = response.json()

    # --------------------------------------------------
    # TOP-LEVEL KEYS
    # --------------------------------------------------

    print("\nTop-level sections:")
    print(list(profile.keys()))

    # --------------------------------------------------
    # PRIMARY TEAM
    # --------------------------------------------------

    primary_team = profile.get("primaryTeam")

    print("\nPrimary team:")
    print(primary_team)

    # --------------------------------------------------
    # COUNTRY / NATIONAL TEAM CANDIDATES
    # --------------------------------------------------

    print("\nPossible country/national-team information:")

    for key in profile.keys():

        key_lower = key.lower()

        if (
            "country" in key_lower
            or "national" in key_lower
            or "international" in key_lower
        ):
            print(f"{key}:")
            print(profile[key])

    # --------------------------------------------------
    # CAREER
    # --------------------------------------------------

    career = profile.get("career")

    print("\nCareer:")
    print(career)

    print("\n")
