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

STATE_FILE = "bot_state.json"


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
# LOAD BOT STATE
# --------------------------------------------------

with open(
    STATE_FILE,
    "r",
    encoding="utf-8"
) as file:

    state = json.load(file)


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

        if (
            home_id not in tracked_teams
            and away_id not in tracked_teams
        ):
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
            "away_name": away.get("name")
        })


# --------------------------------------------------
# CHECK CONFIRMED LINEUPS
# --------------------------------------------------

print("=" * 70)
print("CONFIRMED LINEUP CHECK")
print("=" * 70)
print()


state_changed = False


for match in relevant_matches:

    match_id = str(
        match["match_id"]
    )

    print(
        f"Checking: "
        f"{match['home_name']} vs "
        f"{match['away_name']}"
    )

    # ----------------------------------------------
    # GET MATCH DETAILS
    # ----------------------------------------------

    details_response = requests.get(
        MATCH_DETAILS_URL,
        params={
            "matchId": match["match_id"]
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

    # ----------------------------------------------
    # GET LINEUP
    # ----------------------------------------------

    lineup = (
        details
        .get("content", {})
        .get("lineup")
    )

    if not lineup:

        print(
            "  No lineup data available."
        )

        print()

        continue

    # ----------------------------------------------
    # CHECK LINEUP TYPE
    # ----------------------------------------------

    lineup_type = lineup.get(
        "lineupType"
    )

    print(
        f"  Lineup type: {lineup_type}"
    )

    if lineup_type != "standard":

        print(
            "  ⏳ Lineup is not confirmed yet."
        )

        print()

        continue

    # ----------------------------------------------
    # FIND TRACKED PLAYERS
    # ----------------------------------------------

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

        team_id = team.get("id")
        team_name = team.get("name")

        tracked_players = (
            tracked_teams
            .get(team_id, {})
            .get("players", {})
        )

        if not tracked_players:
            continue

        # Starting XI
        for player in team.get(
            "starters",
            []
        ):

            player_name = player.get(
                "name"
            )

            if player_name in tracked_players:

                found_players.append({
                    "name": player_name,
                    "status": "STARTING XI",
                    "team": team_name
                })

        # Bench
        for player in team.get(
            "subs",
            []
        ):

            player_name = player.get(
                "name"
            )

            if player_name in tracked_players:

                found_players.append({
                    "name": player_name,
                    "status": "BENCH",
                    "team": team_name
                })


    if not found_players:

        print(
            "  No tracked players in "
            "confirmed lineup."
        )

        print()

        continue


    # ----------------------------------------------
    # DUPLICATE PROTECTION
    # ----------------------------------------------

    if match_id not in state[
        "lineup_notifications"
    ]:

        state[
            "lineup_notifications"
        ][match_id] = []


    for player in found_players:

        notification_key = (
            f"{player['name']}|"
            f"{player['status']}"
        )

        if notification_key in state[
            "lineup_notifications"
        ][match_id]:

            print(
                f"  ↪ Already reported: "
                f"{player['name']} "
                f"({player['status']})"
            )

            continue


        # ------------------------------------------
        # CREATE TELEGRAM MESSAGE
        # ------------------------------------------

        lines = [
            "🔵 CONFIRMED LINEUP",
            "",
            f"⚽ {match['home_name']} "
            f"vs {match['away_name']}",
            ""
        ]

        if player["status"] == "STARTING XI":

            lines.append(
                f"✅ {player['name']} "
                f"— STARTING XI"
            )

        else:

            lines.append(
                f"🪑 {player['name']} "
                f"— BENCH"
            )


        message = "\n".join(lines)


        # ------------------------------------------
        # SEND TELEGRAM
        # ------------------------------------------

        telegram_url = (
            f"https://api.telegram.org/"
            f"bot{BOT_TOKEN}/sendMessage"
        )

        telegram_data = {
            "chat_id": CHANNEL,
            "text": message
        }

        telegram_response = requests.post(
            telegram_url,
            data=telegram_data,
            timeout=20
        )

        telegram_response.raise_for_status()


        # ------------------------------------------
        # REMEMBER IT
        # ------------------------------------------

        state[
            "lineup_notifications"
        ][match_id].append(
            notification_key
        )

        state_changed = True

        print(
            f"  📱 Telegram notification sent: "
            f"{player['name']} "
            f"({player['status']})"
        )


    print()


# --------------------------------------------------
# SAVE STATE
# --------------------------------------------------

if state_changed:

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            state,
            file,
            indent=4,
            ensure_ascii=False
        )

    print(
        "💾 Bot state updated."
    )

else:

    print(
        "💾 No state changes."
    )


print()
print("=" * 70)
print("LINEUP MONITORING COMPLETE")
print("=" * 70)
