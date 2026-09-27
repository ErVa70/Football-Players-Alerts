import requests
import json
from collections import defaultdict


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
# HELPER: GET PLAYER COUNTRY
# --------------------------------------------------

def get_country(profile):
    for item in profile.get("playerInformation", []):
        if item.get("title") == "Country":

            value = item.get("value") or {}

            return {
                "name": value.get("fallback"),
                "code": item.get("countryCode")
            }

    return {
        "name": None,
        "code": None
    }


# --------------------------------------------------
# PROCESS EACH PLAYER
# --------------------------------------------------

for player in players:

    name = player["name"]
    player_id = player["fotmob_id"]

    print("=" * 70)
    print(f"PLAYER: {name}")
    print(f"FOTMOB ID: {player_id}")
    print("=" * 70)

    # --------------------------------------------------
    # GET PLAYER PROFILE
    # --------------------------------------------------

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

    current_team_id = primary_team.get("teamId")
    current_team_name = primary_team.get("teamName")

    print(
        f"\nCurrent club: "
        f"{current_team_name} ({current_team_id})"
    )

    # --------------------------------------------------
    # COUNTRY
    # --------------------------------------------------

    country = get_country(profile)

    print(
        f"Country: "
        f"{country['name']} ({country['code']})"
    )

    # --------------------------------------------------
    # FIND TEAMS REPRESENTED IN RECENT MATCHES
    # --------------------------------------------------

    represented_teams = defaultdict(lambda: {
        "name": None,
        "appearances": 0,
        "leagues": set()
    })

    for match in profile.get("recentMatches") or []:

        team_id = match.get("teamId")
        team_name = match.get("teamName")

        if team_id is None or team_name is None:
            continue

        represented_teams[team_id]["name"] = team_name
        represented_teams[team_id]["appearances"] += 1

        league_name = match.get("leagueName")

        if league_name:
            represented_teams[team_id]["leagues"].add(
                league_name
            )

    # --------------------------------------------------
    # PRINT REPRESENTED TEAMS
    # --------------------------------------------------

    print("\nTeams represented in recent matches:")

    for team_id, team_data in represented_teams.items():

        leagues = ", ".join(
            sorted(team_data["leagues"])
        )

        print(
            f"  - {team_data['name']} "
            f"({team_id}) | "
            f"{team_data['appearances']} matches | "
            f"{leagues}"
        )

    # --------------------------------------------------
    # TRY TO IDENTIFY NATIONAL TEAM
    # --------------------------------------------------

    national_team = None

    if country["name"]:

        for team_id, team_data in represented_teams.items():

            if (
                team_data["name"].strip().lower()
                == country["name"].strip().lower()
            ):
                national_team = {
                    "id": team_id,
                    "name": team_data["name"]
                }
                break

    print("\nDetected national team:")

    if national_team:

        print(
            f"  ✅ {national_team['name']} "
            f"({national_team['id']})"
        )

    else:

        print(
            "  ❌ Could not automatically identify "
            "a national team from recent matches."
        )

    print()
