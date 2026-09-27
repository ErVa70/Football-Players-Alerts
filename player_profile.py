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

    print("=" * 70)
    print(f"PLAYER: {name}")
    print(f"FOTMOB ID: {player_id}")
    print("=" * 70)

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
    # CURRENT CLUB
    # --------------------------------------------------

    primary_team = profile.get("primaryTeam") or {}

    print(
        f"\nClub: "
        f"{primary_team.get('teamName')} "
        f"({primary_team.get('teamId')})"
    )

    # --------------------------------------------------
    # COUNTRY
    # --------------------------------------------------

    country = None
    country_code = None

    for item in profile.get("playerInformation", []):

        if item.get("title") == "Country":

            value = item.get("value") or {}

            country = value.get("fallback")
            country_code = item.get("countryCode")

            break

    print(
        f"Country: {country} "
        f"({country_code})"
    )

    # --------------------------------------------------
    # RECENT MATCHES
    # --------------------------------------------------

    recent_matches = profile.get("recentMatches") or []

    print(f"\nRecent matches found: {len(recent_matches)}")

    for match in recent_matches:

        print(json.dumps(match, ensure_ascii=False))

    print("\n")
