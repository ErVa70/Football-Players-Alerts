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
print(f"CHECKING FOTMOB MATCHES FOR: {today}")
print("=" * 70)
print()


# --------------------------------------------------
# LOAD RESOLVED PLAYERS
# --------------------------------------------------

with open("players_resolved.json", "r", encoding="utf-8") as file:
    data = json.load(file)

players = data["players"]

print(f"Loaded players: {len(players)}")
print()


# --------------------------------------------------
# GET TODAY'S MATCHES
# --------------------------------------------------

try:

    response = requests.get(
        MATCHES_URL,
        params={
            "date": today
        },
        headers=HEADERS,
        timeout=20
    )

    print("HTTP status:", response.status_code)
    print("Content-Type:", response.headers.get("Content-Type"))
    print()

    response.raise_for_status()

    matches_data = response.json()

except Exception as error:

    print("❌ Failed to retrieve today's matches:")
    print(error)
    raise SystemExit(1)


# --------------------------------------------------
# BASIC RESPONSE INFORMATION
# --------------------------------------------------

print("FotMob response type:")
print(type(matches_data).__name__)
print()

if isinstance(matches_data, dict):

    print("Top-level keys:")
    print(list(matches_data.keys()))
    print()

elif isinstance(matches_data, list):

    print(f"Response contains {len(matches_data)} top-level items.")
    print()


# --------------------------------------------------
# SHOW STRUCTURE
# --------------------------------------------------

print("=" * 70)
print("RESPONSE STRUCTURE")
print("=" * 70)

if isinstance(matches_data, dict):

    for key, value in matches_data.items():

        print()
        print(f"KEY: {key}")
        print(f"TYPE: {type(value).__name__}")

        if isinstance(value, list):

            print(f"LENGTH: {len(value)}")

            if value:
                print("FIRST ITEM:")

                print(
                    json.dumps(
                        value[0],
                        indent=2,
                        ensure_ascii=False
                    )[:4000]
                )

        elif isinstance(value, dict):

            print(
                json.dumps(
                    value,
                    indent=2,
                    ensure_ascii=False
                )[:4000]
            )

        else:

            print(value)

        print("-" * 70)


elif isinstance(matches_data, list):

    for item in matches_data[:3]:

        print(
            json.dumps(
                item,
                indent=2,
                ensure_ascii=False
            )[:4000]
        )

        print("-" * 70)


else:

    print(matches_data)


print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
