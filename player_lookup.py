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

search_url = "https://www.fotmob.com/api/data/search/suggest"


# --------------------------------------------------
# SEARCH FOR EACH PLAYER
# --------------------------------------------------

for player in players:

    name = player["name"]

    print("=" * 50)
    print(f"Searching FotMob for: {name}")

    response = requests.get(
        search_url,
        params={
            "term": name,
            "hits": 5,
            "lang": "en"
        },
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    results = response.json()

    print()

    print(results)
    print()
