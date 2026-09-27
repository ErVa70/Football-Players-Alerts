import json
import time
import unicodedata
import requests


SEARCH_URL = "https://www.fotmob.com/api/data/search/suggest"
PLAYER_URL = "https://www.fotmob.com/api/data/playerData"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# --------------------------------------------------
# MANUAL PLAYER OVERRIDES
# --------------------------------------------------
#
# These players have multiple exact-name matches
# on FotMob. These IDs select the former Barcelona
# player we actually want.
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


# --------------------------------------------------
# NORMALIZE TEXT
# --------------------------------------------------

def normalize(text):
    """
    Makes name comparison more tolerant of
    accents and capitalization.

    Example:
        Ferran Torres
        Ferrán Torres

    become equivalent.
    """

    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    return text.strip().lower()


# --------------------------------------------------
# SEARCH FOTMOB
# --------------------------------------------------

def search_entities(term):

    response = requests.get(
        SEARCH_URL,
        params={
            "term": term,
            "hits": 20,
            "lang": "en"
        },
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    groups = response.json()

    results = []

    for group in groups:

        for suggestion in group.get(
            "suggestions",
            []
        ):

            # Avoid duplicates between
            # "All" and "Players"/"Teams".
            entity_id = suggestion.get("id")

            if any(
                item.get("id") == entity_id
                and item.get("type") == suggestion.get("type")
                for item in results
            ):
                continue

            results.append(suggestion)

    return results


# --------------------------------------------------
# FIND PLAYER
# --------------------------------------------------

def find_player(name):

    candidates = search_entities(name)

    # Manual selection for known ambiguous names.
    if name in MANUAL_OVERRIDES:

        selected_id = MANUAL_OVERRIDES[name]

        for candidate in candidates:

            if (
                candidate.get("type") == "player"
                and str(candidate.get("id"))
                == str(selected_id)
            ):
                return candidate

        return None

    # Normal exact-name matching.
    normalized_name = normalize(name)

    exact_matches = [
        candidate
        for candidate in candidates
        if (
            candidate.get("type") == "player"
            and not candidate.get("isCoach")
            and normalize(
                candidate.get("name", "")
            ) == normalized_name
        )
    ]

    if len(exact_matches) == 1:
        return exact_matches[0]

    return None


# --------------------------------------------------
# GET PLAYER PROFILE
# --------------------------------------------------

def get_player_profile(player_id):

    response = requests.get(
        PLAYER_URL,
        params={
            "id": player_id
        },
        headers=HEADERS,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# --------------------------------------------------
# GET COUNTRY FROM PLAYER PROFILE
# --------------------------------------------------

def get_country(profile):

    for item in profile.get(
        "playerInformation",
        []
    ):

        if item.get("title") != "Country":
            continue

        value = item.get("value") or {}

        return {
            "name": value.get("fallback"),
            "code": item.get("countryCode")
        }

    return {
        "name": None,
        "code": None
    }


# --------------------------------------------------
# FIND SENIOR NATIONAL TEAM
# --------------------------------------------------

def find_national_team(
    country_name,
    country_code
):

    if not country_name:
        return None

    # First search by the country's full name.
    search_terms = [
        country_name
    ]

    # If necessary, also try the country code.
    if country_code:
        search_terms.append(country_code)

    for term in search_terms:

        try:
            candidates = search_entities(term)

        except Exception:
            continue

        normalized_term = normalize(term)

        # We want an exact senior-team match.
        for candidate in candidates:

            if candidate.get("type") != "team":
                continue

            candidate_name = candidate.get(
                "name",
                ""
            )

            if normalize(candidate_name) != normalized_term:
                continue

            # This naturally excludes:
            # France (W)
            # France U21
            # France U20
            # etc.
            return {
                "id": int(candidate["id"]),
                "name": candidate_name
            }

    return None


# --------------------------------------------------
# LOAD PLAYERS
# --------------------------------------------------

with open(
    "players.json",
    "r",
    encoding="utf-8"
) as file:

    data = json.load(file)

players = data["players"]

print(
    f"Players to resolve: {len(players)}"
)

print()


# --------------------------------------------------
# NATIONAL TEAM CACHE
# --------------------------------------------------
#
# Many players share the same nationality.
#
# For example:
# Spain → search once
# France → search once
# Portugal → search once
#
# instead of repeating the same search for
# every player.
#

national_team_cache = {}


# --------------------------------------------------
# RESOLVE PLAYERS
# --------------------------------------------------

resolved_players = []

for index, player in enumerate(
    players,
    start=1
):

    name = player["name"]

    print(
        f"[{index:03}/{len(players):03}] "
        f"{name}"
    )

    # ----------------------------------------------
    # FIND PLAYER
    # ----------------------------------------------

    try:

        player_match = find_player(name)

    except Exception as error:

        print(
            f"    ❌ Player search error: "
            f"{error}"
        )

        resolved_players.append({
            "name": name,
            "fotmob_id": None,
            "team_id": None,
            "team_name": None,
            "country": None,
            "country_code": None,
            "national_team_id": None,
            "national_team_name": None,
            "status": "error"
        })

        continue

    if player_match is None:

        print(
            "    ❌ Could not uniquely resolve player."
        )

        resolved_players.append({
            "name": name,
            "fotmob_id": None,
            "team_id": None,
            "team_name": None,
            "country": None,
            "country_code": None,
            "national_team_id": None,
            "national_team_name": None,
            "status": "not_found"
        })

        continue

    player_id = int(
        player_match["id"]
    )

    print(
        f"    ✅ Player ID: {player_id}"
    )

    # ----------------------------------------------
    # GET PLAYER PROFILE
    # ----------------------------------------------

    try:

        profile = get_player_profile(
            player_id
        )

    except Exception as error:

        print(
            f"    ❌ Profile error: "
            f"{error}"
        )

        resolved_players.append({
            "name": name,
            "fotmob_id": player_id,
            "team_id": player_match.get(
                "teamId"
            ),
            "team_name": player_match.get(
                "teamName"
            ),
            "country": None,
            "country_code": None,
            "national_team_id": None,
            "national_team_name": None,
            "status": "error"
        })

        continue

    # ----------------------------------------------
    # CURRENT CLUB
    # ----------------------------------------------

    primary_team = (
        profile.get("primaryTeam")
        or {}
    )

    team_id = primary_team.get(
        "teamId"
    )

    team_name = primary_team.get(
        "teamName"
    )

    print(
        f"    Club: "
        f"{team_name} ({team_id})"
    )

    # ----------------------------------------------
    # NATIONALITY
    # ----------------------------------------------

    country = get_country(
        profile
    )

    country_name = country.get(
        "name"
    )

    country_code = country.get(
        "code"
    )

    print(
        f"    Country: "
        f"{country_name} ({country_code})"
    )

    # ----------------------------------------------
    # NATIONAL TEAM
    # ----------------------------------------------

    cache_key = normalize(
        country_name
    )

    if cache_key in national_team_cache:

        national_team = (
            national_team_cache[
                cache_key
            ]
        )

    else:

        national_team = find_national_team(
            country_name,
            country_code
        )

        national_team_cache[
            cache_key
        ] = national_team

        time.sleep(0.25)

    if national_team:

        print(
            f"    National team: "
            f"{national_team['name']} "
            f"({national_team['id']})"
        )

    else:

        print(
            "    ⚠️ National team "
            "could not be resolved."
        )

    # ----------------------------------------------
    # SAVE PLAYER
    # ----------------------------------------------

    resolved_players.append({
        "name": name,
        "fotmob_id": player_id,
        "team_id": team_id,
        "team_name": team_name,
        "country": country_name,
        "country_code": country_code,
        "national_team_id": (
            national_team["id"]
            if national_team
            else None
        ),
        "national_team_name": (
            national_team["name"]
            if national_team
            else None
        ),
        "status": "resolved"
    })

    print()

    # Be polite to FotMob.
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

not_found = sum(
    player["status"] == "not_found"
    for player in resolved_players
)

errors = sum(
    player["status"] == "error"
    for player in resolved_players
)

unique_club_teams = {
    player["team_id"]
    for player in resolved_players
    if player["team_id"] is not None
}

national_team_players = sum(
    player["national_team_id"] is not None
    for player in resolved_players
)

unique_national_teams = {
    player["national_team_id"]
    for player in resolved_players
    if player["national_team_id"] is not None
}
print(
    "=" * 60
)

print("SUMMARY")

print(
    "=" * 60
)

print(
    f"Total:               {len(players)}"
)

print(
    f"Players resolved:    {resolved}"
)

print(
    f"National teams found: {national_team_players} players"
)

print(
    f"Unique national teams: {len(unique_national_teams)}"
)

print(
    f"Unique club teams:     {len(unique_club_teams)}"
)

print(
    f"National teams found: {national_team_players} players"
)

print(
    f"Unique national teams: {len(unique_national_teams)}"
)

print(
    f"Not found:           {not_found}"
)

print(
    f"Errors:              {errors}"
)
