import os
import json
import requests

MATCH_ID = 5181850

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL = "@formerbarcaplayers"


# --------------------------------------------------
# LOAD FOLLOWED PLAYERS
# --------------------------------------------------

with open("players.json", "r", encoding="utf-8") as file:
    player_data = json.load(file)

followed_players = player_data["players"]


# --------------------------------------------------
# GET MATCH DETAILS
# --------------------------------------------------

url = "https://www.fotmob.com/api/data/matchDetails"

params = {
    "matchId": MATCH_ID
}

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(
    url,
    params=params,
    headers=headers,
    timeout=20
)

response.raise_for_status()

data = response.json()


# --------------------------------------------------
# GET TEAMS
# --------------------------------------------------

general = data.get("general", {})
lineup = data.get("content", {}).get("lineup", {})

match_name = general.get("matchName", "Unknown match")

found_players = []


# --------------------------------------------------
# FIND FOLLOWED PLAYERS
# --------------------------------------------------

for team_key in ["homeTeam", "awayTeam"]:

    team = lineup.get(team_key, {})

    if not team:
        continue

    team_name = team.get("name", "Unknown team")

    for player in team.get("starters", []):

        player_name = player.get("name")

        if player_name in followed_players:

            found_players.append(
                f"• {player_name} — STARTING XI ({team_name})"
            )

    for player in team.get("subs", []):

        player_name = player.get("name")

        if player_name in followed_players:

            found_players.append(
                f"• {player_name} — BENCH ({team_name})"
            )


# --------------------------------------------------
# SEND TELEGRAM MESSAGE
# --------------------------------------------------

if found_players:

    message = (
        "🔵 LINEUP\n\n"
        f"⚽ {match_name}\n\n"
        "👤 Watched players:\n"
        + "\n".join(found_players)
    )

    telegram_url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
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

    print("Telegram response:")
    print(telegram_response.json())

else:

    print("No followed players found in this match.")
