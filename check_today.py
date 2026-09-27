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
#
# A player can belong to:
#   - a club team
#   - a national team
#
# We store both.
#
# Example:
#
# Spain:
#   Lamine Yamal      -> national
#   Ferrán Torres     -> national
#   Fermín López      -> national
#
# Barcelona:
#   Lamine Yamal      -> club
#   João Cancelo      -> club
#   Fermín López      -> club
#

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
    # CLUB
    # ----------------------------------------------

    add_player_to_team(
        player.get("team_id"),
        player.get("team_name"),
        player_name,
        "club"
    )

    # ----------------------------------------------
    # NATIONAL TEAM
    # ----------------------------------------------

    add_player_to_team(
        player.get("national_team_id"),
        player.get("national_team_name"),
        player_name,
        "national"
    )


# --------------------------------------------------
# GET TODAY'S LOCAL DATE
# --------------------------------------------------

now_local = datetime.now(
    LOCAL_TIMEZONE
)

today_local = now_local.date()

fotmob_date = today_local.strftime(
    "%Y%m%d"
)


print("=" * 70)

print(
    f"CHECKING TRACKED MATCHES FOR LOCAL DATE: "
    f"{today_local}"
)

print("=" * 70)
print()

print(
    f"Loaded players: {len(players)}"
)

print(
    f"Tracked teams: {len(tracked_teams)}"
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

        home_id = home.get(
            "id"
        )

        away_id = away.get(
            "id"
        )

        # ------------------------------------------
        # FIND PLAYERS ASSOCIATED WITH HOME TEAM
        # ------------------------------------------

        home_tracked = []

        if home_id in tracked_teams:

            team_info = tracked_teams[
                home_id
            ]

            for player_name, types in (
                team_info["players"].items()
            ):

                home_tracked.append({
                    "name": player_name,
                    "types": sorted(types)
                })


        # ------------------------------------------
        # FIND PLAYERS ASSOCIATED WITH AWAY TEAM
        # ------------------------------------------

        away_tracked = []

        if away_id in tracked_teams:

            team_info = tracked_teams[
                away_id
            ]

            for player_name, types in (
                team_info["players"].items()
            ):

                away_tracked.append({
                    "name": player_name,
                    "types": sorted(types)
                })


        # ------------------------------------------
        # IGNORE IRRELEVANT MATCHES
        # ------------------------------------------

        if not home_tracked and not away_tracked:
            continue


        # ------------------------------------------
        # GET ACTUAL KICKOFF TIME
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


        # ------------------------------------------
        # ONLY TODAY'S LOCAL MATCHES
        # ------------------------------------------

        if kickoff_local.date() != today_local:
            continue


        # ------------------------------------------
        # SAVE MATCH
        # ------------------------------------------

        relevant_matches.append({
            "match_id": match.get(
                "id"
            ),
            "league": league_name,
            "time": kickoff_local.strftime(
                "%d.%m.%Y %H:%M"
            ),
            "home_id": home_id,
            "home_name": home.get(
                "name"
            ),
            "away_id": away_id,
            "away_name": away.get(
                "name"
            ),
            "home_players": home_tracked,
            "away_players": away_tracked
        })


# --------------------------------------------------
# DISPLAY RESULTS
# --------------------------------------------------

print("=" * 70)

print(
    "TODAY'S TRACKED MATCHES"
)

print("=" * 70)
print()


if not relevant_matches:

    print(
        "No tracked players have a club "
        "or national-team match today."
    )

else:

    for match in relevant_matches:

        print(
            f"⚽ {match['home_name']} "
            f"vs "
            f"{match['away_name']}"
        )

        print(
            f"   Competition: "
            f"{match['league']}"
        )

        print(
            f"   Kickoff: "
            f"{match['time']}"
        )

        print(
            f"   Match ID: "
            f"{match['match_id']}"
        )


        if match["home_players"]:

            print(
                f"   🏠 Tracked players "
                f"({match['home_name']}):"
            )

            for player in (
                match["home_players"]
            ):

                types = ", ".join(
                    player["types"]
                )

                print(
                    f"      • "
                    f"{player['name']} "
                    f"[{types}]"
                )


        if match["away_players"]:

            print(
                f"   ✈️ Tracked players "
                f"({match['away_name']}):"
            )

            for player in (
                match["away_players"]
            ):

                types = ", ".join(
                    player["types"]
                )

                print(
                    f"      • "
                    f"{player['name']} "
                    f"[{types}]"
                )


        print()


print("=" * 70)

print(
    f"Relevant matches found: "
    f"{len(relevant_matches)}"
)

print("=" * 70)
