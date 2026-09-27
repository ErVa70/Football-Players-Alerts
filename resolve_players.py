import json
import time
import unicodedata
import requests


SEARCH_URL = "https://www.fotmob.com/api/data/search/suggest"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# MANUAL PLAYER OVERRIDES
# --------------------------------------------------
#
# These are players for whom FotMob returns multiple
# exact-name matches. We explicitly select the correct
# player using their FotMob ID.
#

MANUAL_OVERRIDES = {
    "Marlon Santos": 540113,
    "Borja López": 603463,
    "Neymar": 19533,
    "André Gomes": 361770,
    "Arthur": 654044,
    "Nico González": 1280132,
    "Pablo Torre": 1233404,
    "Álex Collado": 929834,
    "Tomás Marqués": 1777474,
    "Luis Suárez": 40636,
    "João Félix": 794427,
    "Adama Traoré": 493647,
    "Dani Rodríguez": 1367049
}


def normalize(text):
    """
    Makes name comparison more tolerant of accents/case.

    Example:
    Ferran Torres
    Ferrán Torres

    become equivalent.
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    return text.strip().lower()


def search_player(name):
    response = requests.get(
        SEARCH_URL,
        params={
            "term": name,
            "hits": 10,
            "lang": "en"
        },
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    groups = response.json()

    candidates = []

    for group in groups:

        for suggestion in group.get("suggestions", []):

            if suggestion.get("type") != "player":
                continue

            if suggestion.get("isCoach"):
                continue

            # Avoid duplicates between "All" and "Players".
            player_id = suggestion.get("id")

            if any(
                candidate.get("id") == player_id
                for candidate in candidates
            ):
                continue

            candidates.append(suggestion)

    return candidates


# --------------------------------------------------
# LOAD PLAYERS
# --------------------------------------------------

with open("players.json", "r", encoding="utf-8") as file:
    data = json.load(file)

players = data["players"]

print(f"Players to resolve: {len(players)}")
print()


# --------------------------------------------------
# RESOLVE EACH PLAYER
# --------------------------------------------------

resolved_players = []

for index, player in enumerate(players, start=1):

    name = player["name"]

    print(
        f"[{index:03}/{len(players):03}] "
        f"{name}"
    )

    try:
        candidates = search_player(name)

    except Exception as error:

        print(f"    ❌ Search error: {error}")
        print()

        resolved_players.append({
            "name": name,
            "fotmob_id": None,
            "team_id": None,
            "team_name": None,
            "status": "error"
        })

        continue


    # --------------------------------------------------
    # MANUAL OVERRIDE
    # --------------------------------------------------

    if name in MANUAL_OVERRIDES:

        selected_id = MANUAL_OVERRIDES[name]

        selected_candidates = [
            candidate
            for candidate in candidates
            if str(candidate.get("id")) == str(selected_id)
        ]

        if selected_candidates:

            match = selected_candidates[0]

            resolved_players.append({
                "name": name,
                "fotmob_id": int(match["id"]),
                "team_id": match.get("teamId"),
                "team_name": match.get("teamName"),
                "status": "resolved"
            })

            print(
                f"    ✅ Manual selection: "
                f"{match.get('name')} "
                f"→ ID {match.get('id')} "
                f"→ {match.get('teamName')}"
            )

        else:

            print(
                f"    ❌ Manual ID {selected_id} "
                f"was not returned by FotMob."
            )

            resolved_players.append({
                "name": name,
                "fotmob_id": None,
                "team_id": None,
                "team_name": None,
                "status": "error"
            })

        print()

        # Be polite to the endpoint.
        time.sleep(0.25)

        continue


    # --------------------------------------------------
    # NORMAL EXACT-MATCH LOGIC
    # --------------------------------------------------

    normalized_name = normalize(name)

    exact_matches = [
        candidate
        for candidate in candidates
        if normalize(candidate.get("name", "")) == normalized_name
    ]

    if len(exact_matches) == 1:

        match = exact_matches[0]

        resolved_players.append({
            "name": name,
            "fotmob_id": int(match["id"]),
            "team_id": match.get("teamId"),
            "team_name": match.get("teamName"),
            "status": "resolved"
        })

        print(
            f"    ✅ {match.get('name')} "
            f"→ ID {match.get('id')} "
            f"→ {match.get('teamName')}"
        )

    elif len(exact_matches) > 1:

        print("    ⚠️ Multiple exact matches:")

        for candidate in exact_matches:

            print(
                f"       {candidate.get('id')} | "
                f"{candidate.get('name')} | "
                f"{candidate.get('teamName')}"
            )

        resolved_players.append({
            "name": name,
            "fotmob_id": None,
            "team_id": None,
            "team_name": None,
            "status": "ambiguous",
            "candidates": [
                {
                    "id": candidate.get("id"),
                    "name": candidate.get("name"),
                    "team_id": candidate.get("teamId"),
                    "team_name": candidate.get("teamName")
                }
                for candidate in exact_matches
            ]
        })

    else:

        print("    ❌ No exact match found.")

        # Show nearby candidates only when useful.
        for candidate in candidates[:5]:

            print(
                f"       candidate: "
                f"{candidate.get('id')} | "
                f"{candidate.get('name')} | "
                f"{candidate.get('teamName')}"
            )

        resolved_players.append({
            "name": name,
            "fotmob_id": None,
            "team_id": None,
            "team_name": None,
            "status": "not_found"
        })

    print()

    # Be polite to the endpoint.
    time.sleep(0.25)


# --------------------------------------------------
# SAVE RESULTS
# --------------------------------------------------

with open(
    "players_resolved.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        {
            "players": resolved_players
        },
        file,
        indent=4,
        ensure_ascii=False
    )


# --------------------------------------------------
# SUMMARY
# --------------------------------------------------

resolved = sum(
    player["status"] == "resolved"
    for player in resolved_players
)

ambiguous = sum(
    player["status"] == "ambiguous"
    for player in resolved_players
)

not_found = sum(
    player["status"] == "not_found"
    for player in resolved_players
)

errors = sum(
    player["status"] == "error"
    for player in resolved_players
)

print("=" * 60)
print("SUMMARY")
print("=" * 60)

print(f"Total:      {len(players)}")
print(f"Resolved:   {resolved}")
print(f"Ambiguous:  {ambiguous}")
print(f"Not found:  {not_found}")
print(f"Errors:     {errors}")
