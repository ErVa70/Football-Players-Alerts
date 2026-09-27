import json
import requests
from datetime import datetime, timezone, timedelta


MATCHES_URL = "https://www.fotmob.com/api/data/matches"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

# Your local timezone: UTC+03:30
LOCAL_TIMEZONE = timezone(
    timedelta(hours=3, minutes=30)
)


# --------------------------------------------------
# LOAD RESOLVED PLAYERS
# --------------------------------------------------

with open("players_resolved.json", "r", encoding="utf-8") as file:
    data = json.load(file)

players = data["players"]


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


# --------------------------------------------------
# GET TODAY'S LOCAL DATE
# --------------------------------------------------

now_local = datetime.now(LOCAL_TIMEZONE)

today_local = now_local.date()

fotmob_date = today_local.strftime("%Y%m%d")

print("=" * 70)
print(
    f"CHECKING TRACKED MATCHES FOR LOCAL DATE: "
    f"{today_local}"
)
print("=" * 70)
print()

print(f"Loaded players: {len(players)}")
print(f"Tracked club teams: {len(tracked_teams)}")
print()


# --------------------------------------------------
# GET MATCHES FROM FOTMOB
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

for league in matches_data.get("leagues", []):

    league_name = league.get(
        "name",
        "Unknown competition"
    )

    for match in league.get("matches", []):

        home = match.get("home", {})
        away = match.get("away", {})
        status = match.get("status") or {}

        home_id = home.get("id")
        away_id = away.get("id")

        # ------------------------------------------
        # DOES THIS MATCH INVOLVE A TRACKED CLUB?
        # ------------------------------------------

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

        # ------------------------------------------
        # GET ACTUAL KICKOFF TIME
        # ------------------------------------------

        utc_time = status.get("utcTime")

        if not utc_time:
            continue

        kickoff_utc = datetime.fromisoformat(
            utc_time.replace("Z", "+00:00")
        )

        kickoff_local = kickoff_utc.astimezone(
            LOCAL_TIMEZONE
        )

        # ------------------------------------------
        # IMPORTANT:
        # Only keep matches whose LOCAL
        # calendar date is today.
        # ------------------------------------------

        if kickoff_local.date() != today_local:
            continue

        tracked_players = (
            home_players + away_players
        )

        relevant_matches.append({
            "match_id": match.get("id"),
            "league": league_name,
            "time": kickoff_local.strftime(
                "%d.%m.%Y %H:%M"
            ),
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
print("TODAY'S TRACKED CLUB MATCHES")
print("=" * 70)
print()


if not relevant_matches:

    print(
        "No tracked players have a club match today."
    )

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
            print(
                f"      • {player}"
            )

        print()


print("=" * 70)
print(
    f"Relevant matches found: "
    f"{len(relevant_matches)}"
)
print("=" * 70)
