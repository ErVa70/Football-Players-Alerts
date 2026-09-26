import os
import json
import requests
from datetime import datetime, timezone


# --------------------------------------------------
# SETTINGS
# --------------------------------------------------

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = "@formerbarcaplayers"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# LOAD FOLLOWED PLAYERS
# --------------------------------------------------

with open("players.json", "r", encoding="utf-8") as file:
    player_data = json.load(file)

followed_players = player_data["players"]

print("========== FOLLOWED PLAYERS ==========")

for player in followed_players:
    print(f"👤 {player}")

print()


# --------------------------------------------------
# GET TODAY'S MATCHES
# --------------------------------------------------

today = datetime.now(timezone.utc).strftime("%Y%m%d")

matches_url = "https://www.fotmob.com/api/data/matches"

response = requests.get(
    matches_url,
    params={"date": today},
    headers=HEADERS,
    timeout=20
)

response.raise_for_status()

matches_data = response.json()

print(f"========== MATCHES FOR {today} ==========")
print()


# --------------------------------------------------
# CHECK MATCHES
# --------------------------------------------------

found_matches = []

for league in matches_data.get("leagues", []):

    league_name = league.get("name", "Unknown league")

    for match in league.get("matches", []):

        match_id = match.get("id")

        home_team = match.get("home", {}).get("name", "Unknown")
        away_team = match.get("away", {}).get("name", "Unknown")

        print(
            f"Checking: {home_team} vs {away_team}"
        )

        # Get detailed match information
        details_url = (
            "https://www.fotmob.com/api/data/matchDetails"
        )

        details_response = requests.get(
            details_url,
            params={"matchId": match_id},
            headers=HEADERS,
            timeout=20
        )

        if details_response.status_code != 200:
            print("  Could not get match details.")
            continue

        details = details_response.json()

        lineup = (
            details
            .get("content", {})
            .get("lineup", {})
        )

        matched_players = []

        # Check both teams
        for team_key in ["homeTeam", "awayTeam"]:

            team = lineup.get(team_key, {})

            if not team:
                continue

            team_name = team.get("name", "Unknown team")

            # Starters
            for player in team.get("starters", []):

                player_name = player.get("name")

                if player_name in followed_players:

                    matched_players.append(
                        f"• {player_name} — "
                        f"STARTING XI ({team_name})"
                    )

            # Substitutes
            for player in team.get("subs", []):

                player_name = player.get("name")

                if player_name in followed_players:

                    matched_players.append(
                        f"• {player_name} — "
                        f"BENCH ({team_name})"
                    )

        # If we found watched players
        if matched_players:

            found_matches.append(
                {
                    "match_id": match_id,
                    "league": league_name,
                    "home": home_team,
                    "away": away_team,
                    "players": matched_players
                }
            )

            print("  🎯 WATCHED PLAYER FOUND!")

        else:

            print("  Nothing relevant.")

        print()


# --------------------------------------------------
# SEND TELEGRAM NOTIFICATIONS
# --------------------------------------------------

print("========== RESULTS ==========")
print()

if not found_matches:

    print("No watched players found in today's matches.")

else:

    for match in found_matches:

        print(
            f"Sending notification for "
            f"{match['home']} vs {match['away']}"
        )

        message = (
            "🔵 LINEUP\n\n"
            f"⚽ {match['home']} vs {match['away']}\n\n"
            "👤 Watched players:\n"
            + "\n".join(match["players"])
        )

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

        print("  ✅ Telegram message sent!")

print()
print("========== DONE ==========")
