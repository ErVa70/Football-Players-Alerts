import os
import json
import requests
from datetime import datetime, timezone, timedelta


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = "@formerbarcaplayers"

MATCHES_URL = "https://www.fotmob.com/api/data/matches"
MATCH_DETAILS_URL = (
    "https://www.fotmob.com/api/data/matchDetails"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

LOCAL_TIMEZONE = timezone(
    timedelta(hours=3, minutes=30)
)


# --------------------------------------------------
# LOAD PLAYERS
# --------------------------------------------------

with open(
    "players_resolved.json",
    "r",
    encoding="utf-8"
) as file:

    data = json.load(file)

players = data["players"]


# --------------------------------------------------
# BUILD TEAM -> PLAYERS LOOKUP
# --------------------------------------------------

tracked_teams = {}


def add_player_to_team(
    team_id,
    team_name,
    player_name,
    team_type
):

    if team_id is None:
        return

    if team_id not in tracked_teams:

        tracked_teams[team_id] = {
            "name": team_name,
            "players": {}
        }

    if player_name not in tracked_teams[
        team_id
    ]["players"]:

        tracked_teams[
            team_id
        ]["players"][player_name] = set()

    tracked_teams[
        team_id
    ]["players"][player_name].add(
        team_type
    )


for player in players:

    player_name = player["name"]

    # Club
    add_player_to_team(
        player.get("team_id"),
        player.get("team_name"),
        player_name,
        "club"
    )

    # National team
    if player.get(
        "monitor_national_team",
        True
    ):

        add_player_to_team(
            player.get("national_team_id"),
            player.get("national_team_name"),
            player_name,
            "national"
        )


# --------------------------------------------------
# TODAY
# --------------------------------------------------

now_local = datetime.now(
    LOCAL_TIMEZONE
)

today_local = now_local.date()

fotmob_date = today_local.strftime(
    "%Y%m%d"
)

print(
    f"Checking tracked matches for "
    f"{today_local}..."
)

print()


# --------------------------------------------------
# GET TODAY'S MATCHES
# --------------------------------------------------

response = requests.get(
    MATCHES_URL,
    params={
        "date": fotmob_date
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


for league in matches_data.get(
    "leagues",
    []
):

    league_name = league.get(
        "name",
        "Unknown competition"
    )

    for match in league.get(
        "matches",
        []
    ):

        home = match.get(
            "home",
            {}
        )

        away = match.get(
            "away",
            {}
        )

        status = match.get(
            "status"
        ) or {}

        home_id = home.get("id")
        away_id = away.get("id")

        home_players = []

        if home_id in tracked_teams:

            home_players = (
                tracked_teams[
                    home_id
                ]["players"]
            )

        away_players = []

        if away_id in tracked_teams:

            away_players = (
                tracked_teams[
                    away_id
                ]["players"]
            )

        if not home_players and not away_players:
            continue

        utc_time = status.get(
            "utcTime"
        )

        if not utc_time:
            continue

        kickoff_utc = datetime.fromisoformat(
            utc_time.replace(
                "Z",
                "+00:00"
            )
        )

        kickoff_local = (
            kickoff_utc.astimezone(
                LOCAL_TIMEZONE
            )
        )

        if kickoff_local.date() != today_local:
            continue

        relevant_matches.append({
            "match_id": match.get("id"),
            "league": league_name,
            "kickoff": kickoff_local,
            "home_id": home_id,
            "home_name": home.get("name"),
            "away_id": away_id,
            "away_name": away.get("name"),
        })


# --------------------------------------------------
# CHECK LINEUPS
# --------------------------------------------------

print("=" * 70)
print("LINEUP CHECK")
print("=" * 70)
print()


for match in relevant_matches:

    match_id = match["match_id"]

    print(
        f"Checking: "
        f"{match['home_name']} vs "
        f"{match['away_name']}"
    )

    details_response = requests.get(
        MATCH_DETAILS_URL,
        params={
            "matchId": match_id
        },
        headers=HEADERS,
        timeout=20
    )

    if details_response.status_code != 200:

        print(
            "  ⚠️ Could not get match details."
        )

        print()

        continue

    details = details_response.json()

    lineup = (
        details
        .get("content", {})
        .get("lineup")
    )

    if not lineup:

        print(
            "  No lineup data available yet."
        )

        print()

        continue

    found_players = []

    for team_key in [
        "homeTeam",
        "awayTeam"
    ]:

        team = lineup.get(
            team_key
        )

        if not team:
            continue

        team_name = team.get(
            "name"
        )

        # ------------------------------------------
        # STARTING XI
        # ------------------------------------------

        for player in (
            team.get("starters", [])
        ):

            player_name = player.get(
                "name"
            )

            if player_name in tracked_teams.get(
                team.get("id"),
                {}
            ).get(
                "players",
                {}
            ):

                found_players.append({
                    "name": player_name,
                    "status": "STARTING XI",
                    "team": team_name
                })


        # ------------------------------------------
        # BENCH
        # ------------------------------------------

        for player in (
            team.get("subs", [])
        ):

            player_name = player.get(
                "name"
            )

            if player_name in tracked_teams.get(
                team.get("id"),
                {}
            ).get(
                "players",
                {}
            ):

                found_players.append({
                    "name": player_name,
                    "status": "BENCH",
                    "team": team_name
                })


    if not found_players:

        print(
            "  No tracked players found "
            "in lineup."
        )

    else:

        for player in found_players:

            print(
                f"  ✅ {player['name']} "
                f"→ {player['status']} "
                f"({player['team']})"
            )

    print()


print("=" * 70)
print("LINEUP CHECK COMPLETE")
print("=" * 70)
