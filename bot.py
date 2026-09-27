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

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# Your local timezone: UTC+03:30
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

    if player_name not in tracked_teams[team_id]["players"]:

        tracked_teams[team_id]["players"][player_name] = set()

    tracked_teams[team_id]["players"][player_name].add(
        team_type
    )


for player in players:

    player_name = player["name"]

    # ----------------------------------------------
    # CLUB IS ALWAYS MONITORED
    # ----------------------------------------------

    add_player_to_team(
        player.get("team_id"),
        player.get("team_name"),
        player_name,
        "club"
    )

    # ----------------------------------------------
    # NATIONAL TEAM ONLY IF ENABLED
    # ----------------------------------------------

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

        home_id = home.get(
            "id"
        )

        away_id = away.get(
            "id"
        )


        # ------------------------------------------
        # TRACKED HOME PLAYERS
        # ------------------------------------------

        home_tracked = []

        if home_id in tracked_teams:

            team_players = tracked_teams[
                home_id
            ]["players"]

            for player_name, types in (
                team_players.items()
            ):

                home_tracked.append({
                    "name": player_name,
                    "types": types
                })


        # ------------------------------------------
        # TRACKED AWAY PLAYERS
        # ------------------------------------------

        away_tracked = []

        if away_id in tracked_teams:

            team_players = tracked_teams[
                away_id
            ]["players"]

            for player_name, types in (
                team_players.items()
            ):

                away_tracked.append({
                    "name": player_name,
                    "types": types
                })


        # Nothing relevant?
        if not home_tracked and not away_tracked:
            continue


        # ------------------------------------------
        # ACTUAL KICKOFF TIME
        # ------------------------------------------

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

        kickoff_local = kickoff_utc.astimezone(
            LOCAL_TIMEZONE
        )


        # Only today's local matches.
        if kickoff_local.date() != today_local:
            continue


        relevant_matches.append({
            "match_id": match.get("id"),
            "league": league_name,
            "kickoff": kickoff_local,
            "home_name": home.get("name"),
            "away_name": away.get("name"),
            "home_players": home_tracked,
            "away_players": away_tracked
        })


# --------------------------------------------------
# SORT BY KICKOFF
# --------------------------------------------------

relevant_matches.sort(
    key=lambda match: match["kickoff"]
)


# --------------------------------------------------
# CREATE TELEGRAM MESSAGE
# --------------------------------------------------

if not relevant_matches:

    message = (
        "📅 TODAY'S TRACKED MATCHES\n\n"
        "No tracked players have a match today."
    )

else:

    lines = [
        "📅 TODAY'S TRACKED MATCHES",
        ""
    ]

    for match in relevant_matches:

        lines.append(
            f"⚽ {match['home_name']} "
            f"vs "
            f"{match['away_name']}"
        )

        lines.append(
            f"🕐 "
            f"{match['kickoff'].strftime('%H:%M')}"
        )

        lines.append(
            f"🏆 {match['league']}"
        )


        # ------------------------------------------
        # HOME PLAYERS
        # ------------------------------------------

        for player in match["home_players"]:

            types = player["types"]

            if "club" in types:
                label = "club"
            else:
                label = "national team"

            lines.append(
                f"👤 {player['name']} "
                f"({label})"
            )


        # ------------------------------------------
        # AWAY PLAYERS
        # ------------------------------------------

        for player in match["away_players"]:

            types = player["types"]

            if "club" in types:
                label = "club"
            else:
                label = "national team"

            lines.append(
                f"👤 {player['name']} "
                f"({label})"
            )


        lines.append("")


    message = "\n".join(lines)


# --------------------------------------------------
# PRINT MESSAGE
# --------------------------------------------------

print()
print("=" * 70)
print("TELEGRAM MESSAGE")
print("=" * 70)
print()
print(message)
print()


# --------------------------------------------------
# SEND TO TELEGRAM
# --------------------------------------------------

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

print(
    "✅ Telegram message sent successfully!"
)
