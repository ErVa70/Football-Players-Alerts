import json
import requests
from datetime import datetime, timezone


MATCHES_URL = "https://www.fotmob.com/api/data/matches"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# TODAY
# --------------------------------------------------

today = datetime.now(timezone.utc).strftime("%Y%m%d")

print("=" * 70)
print(f"CHECKING TRACKED MATCHES FOR: {today}")
print("=" * 70)
print()


# --------------------------------------------------
# LOAD RESOLVED PLAYERS
# --------------------------------------------------

with open("players_resolved.json", "r", encoding="utf-8") as file:
    data = json.load(file)

players = data["players"]

print(f"Loaded players: {len(players)}")


# --------------------------------------------------
# BUILD TEAM -> PLAYERS LOOKUP
# --------------------------------------------------

tracked_teams = {}

for player in players:

    team_id = player.get("team_id")

    if team_id is None:
        continue

    if team_id not in tracked_teams:
        tracked_teams[team_id] = []

    tracked_teams[team_id].append(
        player["name"]
    )


print(f"Tracked club teams: {len(tracked_teams)}")
print()


# --------------------------------------------------
# GET TODAY'S MATCHES
# --------------------------------------------------

response = requests.get(
    MATCHES_URL,
    params={
        "date": today
    },
    headers=HEADERS,
    timeout=20
)

response.raise_for_status()

matches_data = response.json()


# --------------------------------------------------
# FIND RELEVANT MATCHES
# --------------------------------------------------

relevant_matches = []

for league in matches_data.get("leagues", []):

    league_name = league.get(
        "name",
        "Unknown competition"
    )

    for match in league.get("matches", []):

        home = match.get("home", {})
        away = match.get("away", {})

        home_id = home.get("id")
        away_id = away.get("id")

        home_players = tracked_teams.get(
            home_id,
            []
        )

        away_players = tracked_teams.get(
            away_id,
            []
        )

        if not home_players and not away_players:
            continue

        tracked_players = (
            home_players + away_players
        )

        relevant_matches.append({
            "match_id": match.get("id"),
            "league": league_name,
            "time": match.get("time"),
            "home_id": home_id,
            "home_name": home.get("name"),
            "away_id": away_id,
            "away_name": away.get("name"),
            "tracked_players": tracked_players
        })


# --------------------------------------------------
# DISPLAY RESULTS
# --------------------------------------------------

print("=" * 70)
print("TODAY'S TRACKED MATCHES")
print("=" * 70)
print()


if not relevant_matches:

    print("No tracked players have a club match today.")

else:

    for match in relevant_matches:

        print(
            f"⚽ {match['home_name']} "
            f"vs "
            f"{match['away_name']}"
        )

        print(
            f"   Competition: {match['league']}"
        )

        print(
            f"   Kickoff: {match['time']}"
        )

        print(
            f"   Match ID: {match['match_id']}"
        )

        print("   Tracked players:")

        for player in match["tracked_players"]:
            print(f"      • {player}")

        print()


print("=" * 70)
print(
    f"Relevant matches found: "
    f"{len(relevant_matches)}"
)
print("=" * 70)
