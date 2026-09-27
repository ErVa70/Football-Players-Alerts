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
# GET PLAYER INFORMATION
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

    print("\nPLAYER INFORMATION:")
    print(
        json.dumps(
            profile.get("playerInformation"),
            indent=2,
            ensure_ascii=False
        )
    )

    print("\nMETA:")
    print(
        json.dumps(
            profile.get("meta"),
            indent=2,
            ensure_ascii=False
        )
    )

    print("\nMATCH FILTERS:")
    print(
        json.dumps(
            profile.get("matchFilters"),
            indent=2,
            ensure_ascii=False
        )
    )

    print("\n")
