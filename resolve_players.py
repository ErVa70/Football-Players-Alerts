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

    # Use manual ID for known ambiguous players.
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
# GET COUNTRY
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

    search_terms = [country_name]

    if country_code:
        search_terms.append(country_code)

    for term in search_terms:

        try:
            candidates = search_entities(term)
        except Exception:
            continue

        normalized_term = normalize(term)

        for candidate in candidates:

            if candidate.get("type") != "team":
                continue

            candidate_name = candidate.get(
                "name",
                ""
            )

            if normalize(candidate_name) != normalized_term:
                continue

            # Exact country name means we select
            # the senior team, not:
            # France (W), France U21, etc.
            return {
                "id": int(candidate["id"]),
                "name": candidate_name
            }

    return None


# --------------------------------------------------
# LOAD PLAYERS + SETTINGS
# --------------------------------------------------

with open(
    "players.json",
    "r",
    encoding="utf-8"
) as file:

    data = json.load(file)

players = data["players"]

# Players listed here will NOT have their
# national team monitored.
excluded_national_players = {
    normalize(name)
    for name in data.get(
        "national_team_exclusions",
        []
    )
}

print(
    f"Players to resolve: {len(players)}"
)

print(
    f"National-team exclusions: "
    f"{len(excluded_national_players)}"
)

print()


# --------------------------------------------------
# NATIONAL TEAM CACHE
# --------------------------------------------------

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
    # NATIONAL TEAM MONITORING SETTING
    # ----------------------------------------------

    monitor_national_team = (
        normalize(name)
        not in excluded_national_players
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
            "monitor_national_team": monitor_national_team,
            "status": "error"
        })

        continue

    if player_match is None:

        print(
            "    ❌ Could not resolve player."
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
            "monitor_national_team": monitor_national_team,
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
    # GET PROFILE
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
            "monitor_national_team": monitor_national_team,
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
    # COUNTRY
    # ----------------------------------------------

    country = get_country(profile)

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

    national_team = None

    if monitor_national_team:

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

    else:

        print(
            "    🚫 National-team monitoring: OFF"
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
        "monitor_national_team": monitor_national_team,
        "status": "resolved"
    })

    print()

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

national_teams_found = sum(
    player["national_team_id"] is not None
    for player in resolved_players
)

unique_national_teams = {
    player["national_team_id"]
    for player in resolved_players
    if player["national_team_id"] is not None
}

unique_club_teams = {
    player["team_id"]
    for player in resolved_players
    if player["team_id"] is not None
}

national_monitoring_on = sum(
    player["monitor_national_team"]
    for player in resolved_players
)

national_monitoring_off = sum(
    not player["monitor_national_team"]
    for player in resolved_players
)


# --------------------------------------------------
# SUMMARY
# --------------------------------------------------

print(
    "=" * 60
)

print("SUMMARY")

print(
    "=" * 60
)

print(
    f"Total:                    {len(players)}"
)

print(
    f"Players resolved:         {resolved}"
)

print(
    f"Unique club teams:        "
    f"{len(unique_club_teams)}"
)

print(
    f"National teams found:     "
    f"{national_teams_found} players"
)

print(
    f"Unique national teams:    "
    f"{len(unique_national_teams)}"
)

print(
    f"National monitoring ON:   "
    f"{national_monitoring_on}"
)

print(
    f"National monitoring OFF:  "
    f"{national_monitoring_off}"
)

print(
    f"Not found:                {not_found}"
)

print(
    f"Errors:                   {errors}"
)
