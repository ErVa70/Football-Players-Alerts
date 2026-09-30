import json
import os
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests


# ============================================================
# CONFIG
# ============================================================

FOTMOB_BASE = "https://www.fotmob.com/api/data"

LOCAL_TIMEZONE = timezone(
    timedelta(hours=3, minutes=30)
)

PLAYERS_FILE = "players_resolved.json"
STATE_FILE = "bot_state.json"

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHANNEL = "@formerbarcaplayers"


# ============================================================
# FILE HELPERS
# ============================================================

def load_json(filename, default):
    path = Path(filename)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )


# ============================================================
# FOTMOB
# ============================================================

def fotmob_get(endpoint, params=None):
    url = f"{FOTMOB_BASE}/{endpoint}"

    response = requests.get(
        url,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHANNEL,
            "text": message,
        },
        timeout=30,
    )

    response.raise_for_status()


# ============================================================
# TIME / DATE HELPERS
# ============================================================

def get_local_now():
    return datetime.now(
        timezone.utc
    ).astimezone(
        LOCAL_TIMEZONE
    )


def get_local_today():
    return get_local_now().date()


def get_daily_window():
    """
    Daily Matches window:

        Today 10:00 Tehran
        ->
        Tomorrow 10:00 Tehran
    """

    now = get_local_now()

    window_start = now.replace(
        hour=10,
        minute=0,
        second=0,
        microsecond=0,
    )

    window_end = (
        window_start
        + timedelta(days=1)
    )

    return (
        window_start,
        window_end,
        now,
    )


# ============================================================
# MATCH DISCOVERY
# ============================================================

def get_matches_for_date(date_value):
    date_string = date_value.strftime(
        "%Y%m%d"
    )

    data = fotmob_get(
        "matches",
        {
            "date": date_string
        },
    )

    return data.get(
        "leagues",
        []
    )


def get_today_matches():
    return get_matches_for_date(
        get_local_today()
    )


def collect_matches(leagues):
    matches = []

    for league in leagues:
        for match in league.get(
            "matches",
            []
        ):
            matches.append(match)

    return matches


def parse_match_kickoff(match):
    utc_time = (
        match.get(
            "status",
            {}
        ).get(
            "utcTime"
        )
    )

    if not utc_time:
        return None

    try:
        return (
            datetime.fromisoformat(
                utc_time.replace(
                    "Z",
                    "+00:00"
                )
            ).astimezone(
                LOCAL_TIMEZONE
            )
        )
    except ValueError:
        return None


def get_daily_window_matches(
    window_start,
    window_end,
):
    """
    Fetch both calendar dates because the
    10:00 -> 10:00 window crosses midnight.
    """

    dates_to_fetch = [
        window_start.date(),
        window_end.date(),
    ]

    all_matches = []
    seen_match_ids = set()

    for date_value in dates_to_fetch:

        leagues = get_matches_for_date(
            date_value
        )

        matches = collect_matches(
            leagues
        )

        for match in matches:

            match_id = match.get(
                "id"
            )

            if match_id in seen_match_ids:
                continue

            kickoff = parse_match_kickoff(
                match
            )

            if kickoff is None:
                continue

            if (
                kickoff >= window_start
                and kickoff < window_end
            ):
                all_matches.append(
                    match
                )

                seen_match_ids.add(
                    match_id
                )

    all_matches.sort(
        key=lambda match: (
            parse_match_kickoff(
                match
            )
            or window_start
        )
    )

    return all_matches


# ============================================================
# TRACKED TEAMS
# ============================================================

def build_tracked_teams(players):
    tracked_teams = set()

    for player in players:

        club_id = (
            player.get(
                "team_id"
            )
            or player.get(
                "teamId"
            )
        )

        if club_id is not None:
            tracked_teams.add(
                int(club_id)
            )

        if player.get(
            "monitor_national_team"
        ):
            national_team_id = (
                player.get(
                    "national_team_id"
                )
                or player.get(
                    "nationalTeamId"
                )
            )

            if national_team_id is not None:
                tracked_teams.add(
                    int(national_team_id)
                )

    return tracked_teams


def is_relevant_match(
    match,
    tracked_teams
):
    home = match.get(
        "home",
        {}
    )

    away = match.get(
        "away",
        {}
    )

    home_id = home.get(
        "id"
    )

    away_id = away.get(
        "id"
    )

    if (
        home_id is not None
        and int(home_id)
        in tracked_teams
    ):
        return True

    if (
        away_id is not None
        and int(away_id)
        in tracked_teams
    ):
        return True

    return False


# ============================================================
# PLAYER LOOKUP
# ============================================================

def build_player_lookup(players):
    lookup = {}

    for player in players:

        player_id = player.get(
            "fotmob_id"
        )

        if player_id is not None:
            lookup[int(player_id)] = player

    return lookup


def get_tracked_players_for_match(
    match,
    player_lookup,
):
    """
    Return the tracked players whose current
    club or monitored national team is involved
    in this match.
    """

    home_id = (
        match.get(
            "home",
            {}
        ).get(
            "id"
        )
    )

    away_id = (
        match.get(
            "away",
            {}
        ).get(
            "id"
        )
    )

    tracked_players = []

    for player in player_lookup.values():

        club_id = player.get(
            "team_id"
        )

        national_id = player.get(
            "national_team_id"
        )

        monitor_national = player.get(
            "monitor_national_team",
            True
        )

        matched = False

        # Current club
        if club_id is not None:

            try:
                club_id = int(
                    club_id
                )

                if (
                    home_id is not None
                    and int(home_id)
                    == club_id
                ):
                    matched = True

                elif (
                    away_id is not None
                    and int(away_id)
                    == club_id
                ):
                    matched = True

            except (
                TypeError,
                ValueError
            ):
                pass

        # Monitored national team
        if (
            not matched
            and monitor_national
            and national_id is not None
        ):

            try:
                national_id = int(
                    national_id
                )

                if (
                    home_id is not None
                    and int(home_id)
                    == national_id
                ):
                    matched = True

                elif (
                    away_id is not None
                    and int(away_id)
                    == national_id
                ):
                    matched = True

            except (
                TypeError,
                ValueError
            ):
                pass

        if matched:
            tracked_players.append(
                player["name"]
            )

    return tracked_players


# ============================================================
# DAILY MATCHES POST
# ============================================================

def process_daily_schedule(
    matches,
    state,
    player_lookup,
    window_start,
    window_end,
):
    """
    Publish the Daily Matches post once for the
    current 10:00 -> next-day 10:00 Tehran window.
    """

    now = get_local_now()

    # Do not publish before 10:00.
    if now < window_start:
        print(
            "  ⏳ Daily Matches post is not due yet."
        )

        print(
            "  Window begins at:",
            window_start.strftime(
                "%Y-%m-%d %H:%M"
            )
        )

        return

    window_key = (
        window_start.isoformat()
    )

    # Already posted this exact window.
    if window_key in state[
        "daily_posts"
    ]:
        print(
            "  ↪ Daily schedule already "
            "posted for "
            f"{window_start.strftime('%Y-%m-%d %H:%M')}"
        )

        return

    sections = []

    for match in matches:

        tracked_players = (
            get_tracked_players_for_match(
                match,
                player_lookup,
            )
        )

        if not tracked_players:
            continue

        home_name = (
            match.get(
                "home",
                {}
            ).get(
                "name",
                "Home"
            )
        )

        away_name = (
            match.get(
                "away",
                {}
            ).get(
                "name",
                "Away"
            )
        )

        kickoff = parse_match_kickoff(
            match
        )

        if kickoff:
            time_text = kickoff.strftime(
                "%H:%M"
            )
        else:
            time_text = "TBD"

        section = (
            f"⚽ {home_name} vs {away_name}"
            f" — {time_text}\n"
            f"👤 "
            + ", ".join(
                tracked_players
            )
        )

        sections.append(
            section
        )

    if not sections:
        print(
            "  ℹ️ No relevant matches "
            "inside this 24-hour window."
        )

        state[
            "daily_posts"
        ].append(
            window_key
        )

        return

    window_text = (
        f"{window_start.strftime('%d %b %H:%M')}"
        f" → "
        f"{window_end.strftime('%d %b %H:%M')}"
        f" Tehran"
    )

    message = (
        "📅 DAILY MATCHES\n\n"
        f"🕙 {window_text}\n\n"
        + "\n\n".join(
            sections
        )
    )

    send_telegram(
        message
    )

    state[
        "daily_posts"
    ].append(
        window_key
    )

    print(
        "  📱 Daily schedule "
        "notification sent."
    )


# ============================================================
# MATCH DETAILS
# ============================================================

def get_match_details(match_id):
    return fotmob_get(
        "matchDetails",
        {
            "matchId": match_id
        },
    )


# ============================================================
# LINEUP HELPERS
# ============================================================

def extract_lineup_players(lineup):
    players = {}

    if not lineup:
        return players

    for side_key in [
        "homeTeam",
        "awayTeam",
    ]:

        side = lineup.get(
            side_key
        )

        if not side:
            continue

        for role, role_name in [
            (
                "starters",
                "STARTING XI",
            ),
            (
                "subs",
                "BENCH",
            ),
        ]:

            for player in side.get(
                role,
                []
            ):

                player_id = player.get(
                    "id"
                )

                if player_id is None:
                    continue

                players[
                    int(player_id)
                ] = {
                    "role": role_name,
                    "name": player.get(
                        "name",
                        "Unknown"
                    ),
                    "team_id": side.get(
                        "id"
                    ),
                    "team_name": side.get(
                        "name"
                    ),
                    "timeSubbedOn": player.get(
                        "timeSubbedOn"
                    ),
                    "timeSubbedOff": player.get(
                        "timeSubbedOff"
                    ),
                    "events": player.get(
                        "events"
                    ) or {},
                }

    return players


def process_confirmed_lineup(
    match,
    details,
    state,
    player_lookup,
):
    match_id = str(
        match["id"]
    )

    content = details.get(
        "content",
        {}
    )

    lineup = content.get(
        "lineup"
    )

    if not lineup:
        print(
            "  No lineup data available."
        )

        return

    lineup_type = lineup.get(
        "lineupType"
    )

    print(
        f"  Lineup type: {lineup_type}"
    )

    if lineup_type != "standard":
        print(
            "  ⏳ Lineup is not confirmed yet."
        )

        return

    lineup_players = (
        extract_lineup_players(
            lineup
        )
    )

    reported = (
        state[
            "lineup_notifications"
        ].setdefault(
            match_id,
            []
        )
    )

    for (
        player_id,
        lineup_player
    ) in lineup_players.items():

        if player_id not in player_lookup:
            continue

        player = player_lookup[
            player_id
        ]

        notification_key = (
            f"{player['name']}|"
            f"{lineup_player['role']}"
        )

        if notification_key in reported:

            print(
                f"  ↪ Already reported: "
                f"{player['name']} "
                f"({lineup_player['role']})"
            )

            continue

        home_name = (
            match.get(
                "home",
                {}
            ).get(
                "name",
                "Home"
            )
        )

        away_name = (
            match.get(
                "away",
                {}
            ).get(
                "name",
                "Away"
            )
        )

        message = (
            "🔵 CONFIRMED LINEUP\n\n"
            f"⚽ {home_name} vs "
            f"{away_name}\n\n"
            f"✅ {player['name']} — "
            f"{lineup_player['role']}"
        )

        send_telegram(
            message
        )

        print(
            f"  📱 Telegram notification sent: "
            f"{player['name']} "
            f"({lineup_player['role']})"
        )

        reported.append(
            notification_key
        )


# ============================================================
# EVENT HELPERS
# ============================================================

def get_event_key(event):

    event_id = event.get(
        "eventId"
    )

    if event_id is not None:
        return f"id:{event_id}"

    event_type = str(
        event.get(
            "type",
            "unknown"
        )
    )

    minute = str(
        event.get(
            "time",
            ""
        )
    )

    player = (
        event.get(
            "player"
        )
        or {}
    )

    player_id = player.get(
        "id",
        ""
    )

    swaps = (
        event.get(
            "swap"
        )
        or []
    )

    swap_ids = ",".join(
        str(
            x.get(
                "id",
                ""
            )
        )
        for x in swaps
        if isinstance(
            x,
            dict
        )
    )

    card = str(
        event.get(
            "card",
            ""
        )
    )

    return (
        f"{event_type}|"
        f"{minute}|"
        f"{player_id}|"
        f"{swap_ids}|"
        f"{card}"
    )


def get_event_player_id(event):

    player = (
        event.get(
            "player"
        )
        or {}
    )

    player_id = player.get(
        "id"
    )

    if player_id is None:
        return None

    try:
        return int(
            player_id
        )
    except (
        TypeError,
        ValueError
    ):
        return None


def get_swap_players(event):

    swap_players = []

    for swap in (
        event.get(
            "swap"
        )
        or []
    ):

        if not isinstance(
            swap,
            dict
        ):
            continue

        player_id = swap.get(
            "id"
        )

        name = swap.get(
            "name"
        )

        if player_id is not None:

            try:
                player_id = int(
                    player_id
                )
            except (
                TypeError,
                ValueError
            ):
                pass

        swap_players.append({
            "id": player_id,
            "name": name or "Unknown",
        })

    return swap_players


def get_minute(event):

    minute = event.get(
        "time"
    )

    if minute is None:
        minute = event.get(
            "timeStr",
            ""
        )

    overload = event.get(
        "overloadTime"
    )

    if overload:
        return (
            f"{minute}+"
            f"{overload}'"
        )

    return f"{minute}'"


def normalize_card(card):

    if not card:
        return "CARD"

    card = str(
        card
    ).strip().lower()

    if (
        "second" in card
        and "yellow" in card
    ):
        return "SECOND YELLOW"

    if "red" in card:
        return "RED CARD"

    if "yellow" in card:
        return "YELLOW CARD"

    return str(
        card
    ).upper()


def is_penalty_event(event):

    text_parts = [
        str(
            event.get(
                "goalDescription",
                ""
            )
        ),
        str(
            event.get(
                "nameStr",
                ""
            )
        ),
        str(
            event.get(
                "type",
                ""
            )
        ),
    ]

    combined = " ".join(
        text_parts
    ).lower()

    return "penalty" in combined


def is_own_goal(event):

    own_goal = event.get(
        "ownGoal"
    )

    if own_goal is True:
        return True

    description = str(
        event.get(
            "goalDescription",
            ""
        )
    ).lower()

    return (
        "own goal"
        in description
    )


def get_assist_info(event):
    """Return the credited assist player's ID and name when available."""

    assist = event.get(
        "assist"
    )

    assist_id = None
    assist_name = None

    if isinstance(
        assist,
        dict
    ):
        assist_id = (
            assist.get("id")
            or assist.get("playerId")
            or assist.get("assistPlayerId")
            or assist.get("personId")
        )

        assist_name = (
            assist.get("name")
            or assist.get("playerName")
            or assist.get("fullName")
        )

    elif isinstance(
        assist,
        str
    ):
        assist_name = assist

    assist_id = (
        assist_id
        or event.get("assistPlayerId")
        or event.get("assistPersonId")
        or event.get("assistId")
    )

    assist_name = (
        assist_name
        or event.get("assistName")
        or event.get("assistPlayerName")
        or event.get("assistPlayerFullName")
    )

    try:
        if assist_id is not None:
            assist_id = int(assist_id)
    except (TypeError, ValueError):
        assist_id = None

    return assist_id, assist_name


def normalize_person_name(value):
    """Normalize names so ID-less assist names can still be matched."""

    if value is None:
        return ""

    text = unicodedata.normalize(
        "NFKD",
        str(value)
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    return " ".join(
        text.casefold().split()
    )


def find_tracked_player_by_name(
    name,
    player_lookup,
):
    """Find a tracked player from a credited assist name."""

    target = normalize_person_name(name)

    if not target:
        return None, None

    for player_id, player in player_lookup.items():
        if (
            normalize_person_name(
                player.get("name")
            )
            == target
        ):
            return player_id, player

    return None, None


# ============================================================
# SUBSTITUTION HELPERS
# ============================================================

def build_substitution_info(details):

    lineup = (
        details.get(
            "content",
            {}
        ).get(
            "lineup"
        )
        or {}
    )

    info = {}

    for side_key in [
        "homeTeam",
        "awayTeam"
    ]:

        side = lineup.get(
            side_key
        )

        if not side:
            continue

        for role in [
            "starters",
            "subs"
        ]:

            for player in side.get(
                role,
                []
            ):

                player_id = player.get(
                    "id"
                )

                if player_id is None:
                    continue

                try:
                    player_id = int(
                        player_id
                    )
                except (
                    TypeError,
                    ValueError
                ):
                    continue

                events = (
                    player.get(
                        "events"
                    )
                    or {}
                )

                sub = (
                    events.get(
                        "sub"
                    )
                    or {}
                )

                info[player_id] = {
                    "name": player.get(
                        "name",
                        "Unknown"
                    ),
                    "initial_role": role,
                    "timeSubbedOn": player.get(
                        "timeSubbedOn"
                    ),
                    "timeSubbedOff": player.get(
                        "timeSubbedOff"
                    ),
                    "subbedIn": sub.get(
                        "subbedIn"
                    ),
                    "subbedOut": sub.get(
                        "subbedOut"
                    ),
                }

    return info


def determine_substitution(
    event,
    substitution_info
):

    swap_players = (
        get_swap_players(
            event
        )
    )

    if not swap_players:
        return None, None

    players_in = []
    players_out = []

    event_minute = event.get(
        "time"
    )

    for player in swap_players:

        player_id = player["id"]

        info = substitution_info.get(
            player_id
        )

        if not info:
            continue

        time_on = info.get(
            "timeSubbedOn"
        )

        time_off = info.get(
            "timeSubbedOff"
        )

        subbed_in = (
            info.get(
                "subbedIn"
            ) == event_minute
            or time_on == event_minute
        )

        subbed_out = (
            info.get(
                "subbedOut"
            ) == event_minute
            or time_off == event_minute
        )

        if subbed_in:
            players_in.append(
                player["name"]
            )

        elif subbed_out:
            players_out.append(
                player["name"]
            )

    if (
        len(players_in) == 1
        and len(players_out) == 1
    ):
        return (
            players_in[0],
            players_out[0]
        )

    starters = []
    bench = []

    for player in swap_players:

        info = substitution_info.get(
            player["id"]
        )

        if not info:
            continue

        if (
            info.get(
                "initial_role"
            ) == "subs"
        ):
            bench.append(
                player["name"]
            )
        else:
            starters.append(
                player["name"]
            )

    if (
        len(bench) == 1
        and len(starters) == 1
    ):
        return (
            bench[0],
            starters[0]
        )

    return None, None



# ============================================================
# LIVE EVENT PROCESSING
# ============================================================

def normalize_event_text(event):
    parts = [
        event.get("type"),
        event.get("goalDescription"),
        event.get("nameStr"),
        event.get("card"),
        event.get("cardDescription"),
        event.get("description"),
    ]

    return " ".join(
        str(part)
        for part in parts
        if part is not None
    ).strip().lower()


def is_disallowed_goal_event(event):
    text = normalize_event_text(event)

    return any(
        term in text
        for term in [
            "disallowed",
            "disallow",
            "goal disallowed",
            "goal cancelled",
            "goal canceled",
            "goal overturned",
            "goal overruled",
            "goal annulled",
            "goal annul",
        ]
    )


def is_penalty_missed_event(event):
    text = normalize_event_text(event)

    if "penalty" not in text:
        return False

    if "scored" in text or "goal" in text:
        return False

    return any(
        term in text
        for term in [
            "miss",
            "saved",
            "save",
            "off target",
            "failed",
        ]
    )


def get_event_score_before(event):
    home_score = event.get("homeScore")
    away_score = event.get("awayScore")

    try:
        if home_score is not None and away_score is not None:
            return int(home_score), int(away_score)
    except (TypeError, ValueError):
        pass

    return None, None


def get_event_score_after(event):
    home_score, away_score = get_event_score_before(event)

    if home_score is None or away_score is None:
        return None

    is_home = event.get("isHome")
    own_goal = is_own_goal(event)

    if is_home is True:
        if own_goal:
            away_score += 1
        else:
            home_score += 1

    elif is_home is False:
        if own_goal:
            home_score += 1
        else:
            away_score += 1

    else:
        return None

    return home_score, away_score


def format_score(home_score, away_score):
    if home_score is None or away_score is None:
        return None

    return f"{home_score} - {away_score}"


def get_current_score_text(status):
    return status.get("scoreStr") or ""


def process_match_events(
    match,
    details,
    state,
    player_lookup,
):

    match_id = str(match["id"])

    header = details.get(
        "header",
        {}
    )

    status = (
        header.get(
            "status"
        )
        or {}
    )

    if not status.get("started"):
        return

    content = details.get(
        "content",
        {}
    )

    match_facts = (
        content.get(
            "matchFacts"
        )
        or {}
    )

    events_container = (
        match_facts.get(
            "events"
        )
        or {}
    )

    events = (
        events_container.get(
            "events"
        )
        or []
    )

    reported = (
        state[
            "match_events"
        ].setdefault(
            match_id,
            []
        )
    )

    substitution_info = (
        build_substitution_info(
            details
        )
    )

    home_name = (
        match.get(
            "home",
            {}
        ).get(
            "name",
            "Home"
        )
    )

    away_name = (
        match.get(
            "away",
            {}
        ).get(
            "name",
            "Away"
        )
    )

    for event in events:

        if not isinstance(event, dict):
            continue

        event_key = get_event_key(event)

        event_type = str(
            event.get(
                "type",
                ""
            )
        ).strip().lower()

        minute = get_minute(event)

        # ----------------------------------------------------
        # GOAL DISALLOWED / OVERTURNED
        # ----------------------------------------------------

        if is_disallowed_goal_event(event):

            scorer_id = get_event_player_id(event)

            assist_id, assist_name = get_assist_info(event)

            tracked_scorer = (
                scorer_id in player_lookup
            )

            tracked_assist = (
                assist_id in player_lookup
            )

            if not tracked_assist and assist_name:
                (
                    assist_id,
                    _assist_player,
                ) = find_tracked_player_by_name(
                    assist_name,
                    player_lookup,
                )

                tracked_assist = (
                    assist_id is not None
                )

            correction_key = (
                f"{event_key}|disallowed"
            )

            if (
                correction_key not in reported
                and (tracked_scorer or tracked_assist)
            ):

                scorer_name = (
                    event.get(
                        "player",
                        {}
                    ).get(
                        "name",
                        "Unknown"
                    )
                )

                before_home, before_away = (
                    get_event_score_before(event)
                )

                corrected_score = format_score(
                    before_home,
                    before_away,
                )

                if corrected_score is None:
                    corrected_score = (
                        get_current_score_text(
                            status
                        )
                    )

                message = (
                    "🚫 GOAL DISALLOWED\n\n"
                    f"⚽ {home_name} vs {away_name}\n\n"
                    f"👤 {scorer_name}\n"
                    f"⏱️ {minute}"
                )

                if corrected_score:
                    message += (
                        f"\n📊 Corrected score: "
                        f"{corrected_score}"
                    )

                reason = (
                    event.get(
                        "goalDescription"
                    )
                    or event.get(
                        "cardDescription"
                    )
                )

                if reason:
                    message += (
                        f"\nℹ️ {reason}"
                    )

                send_telegram(message)

                print(
                    f"  📱 Disallowed-goal notification sent: "
                    f"{scorer_name}"
                )

                reported.append(
                    correction_key
                )

            continue

        # ----------------------------------------------------
        # GOAL + ASSIST
        # ----------------------------------------------------

        if event_type == "goal":

            assist_id, assist_name = get_assist_info(
                event
            )

            tracked_assist_id = None
            tracked_assist = None

            if assist_id in player_lookup:
                tracked_assist_id = assist_id
                tracked_assist = player_lookup[
                    assist_id
                ]

            elif assist_name:
                (
                    tracked_assist_id,
                    tracked_assist,
                ) = find_tracked_player_by_name(
                    assist_name,
                    player_lookup,
                )

            player_id = get_event_player_id(
                event
            )

            # ---------------------------------------------
            # GOAL SCORER
            # ---------------------------------------------

            if (
                player_id in player_lookup
                and event_key not in reported
            ):

                player = player_lookup[
                    player_id
                ]

                if is_own_goal(event):
                    title = "🔴 OWN GOAL"
                elif is_penalty_event(event):
                    title = "⚽ PENALTY GOAL"
                else:
                    title = "⚽ GOAL"

                message = (
                    f"{title}\n\n"
                    f"⚽ {home_name} vs {away_name}\n\n"
                    f"👤 {player['name']}\n"
                    f"⏱️ {minute}"
                )

                if assist_name:
                    message += (
                        f"\n🅰️ Assist: {assist_name}"
                    )

                after_home, after_away = (
                    get_event_score_after(event)
                )

                score_after = format_score(
                    after_home,
                    after_away,
                )

                if score_after is None:
                    score_after = (
                        get_current_score_text(
                            status
                        )
                    )

                if score_after:
                    message += (
                        f"\n📊 Score: {score_after}"
                    )

                send_telegram(message)

                print(
                    f"  📱 Goal notification sent: "
                    f"{player['name']}"
                )

                reported.append(
                    event_key
                )

            # ---------------------------------------------
            # TRACKED ASSISTER
            # ---------------------------------------------

            if tracked_assist_id is not None:

                assist_key = (
                    f"{event_key}|assist|"
                    f"{tracked_assist_id}"
                )

                if assist_key not in reported:

                    scorer_name = (
                        event.get(
                            "player",
                            {}
                        ).get(
                            "name",
                            "Unknown"
                        )
                    )

                    message = (
                        "🅰️ ASSIST\n\n"
                        f"⚽ {home_name} vs {away_name}\n\n"
                        f"👤 {tracked_assist['name']}\n"
                        f"🎯 For: {scorer_name}\n"
                        f"⏱️ {minute}"
                    )

                    after_home, after_away = (
                        get_event_score_after(event)
                    )

                    score_after = format_score(
                        after_home,
                        after_away,
                    )

                    if score_after is None:
                        score_after = (
                            get_current_score_text(
                                status
                            )
                        )

                    if score_after:
                        message += (
                            f"\n📊 Score: {score_after}"
                        )

                    send_telegram(message)

                    print(
                        f"  📱 Assist notification sent: "
                        f"{tracked_assist['name']}"
                    )

                    reported.append(
                        assist_key
                    )

            continue

        # ----------------------------------------------------
        # PENALTY MISSED
        # ----------------------------------------------------

        if is_penalty_missed_event(event):

            player_id = get_event_player_id(
                event
            )

            if player_id not in player_lookup:
                continue

            penalty_key = (
                f"penalty-missed|"
                f"{player_id}|"
                f"{event.get('time', '')}"
            )

            if penalty_key in reported:
                continue

            player = player_lookup[
                player_id
            ]

            message = (
                "❌ PENALTY MISSED\n\n"
                f"⚽ {home_name} vs {away_name}\n\n"
                f"👤 {player['name']}\n"
                f"⏱️ {minute}"
            )

            description = (
                event.get(
                    "goalDescription"
                )
                or event.get(
                    "nameStr"
                )
            )

            if description:
                message += (
                    f"\nℹ️ {description}"
                )

            send_telegram(message)

            print(
                f"  📱 Missed-penalty notification sent: "
                f"{player['name']}"
            )

            reported.append(
                penalty_key
            )

            continue

        if event_key in reported:
            continue

        # ----------------------------------------------------
        # CARD
        # ----------------------------------------------------

        if event_type == "card":

            player_id = get_event_player_id(
                event
            )

            if player_id not in player_lookup:
                continue

            player = player_lookup[
                player_id
            ]

            card = normalize_card(
                event.get(
                    "card"
                )
            )

            if card not in {
                "YELLOW CARD",
                "RED CARD",
                "SECOND YELLOW",
            }:
                continue

            if card in {
                "RED CARD",
                "SECOND YELLOW",
            }:
                emoji = "🟥"
            else:
                emoji = "🟨"

            message = (
                f"{emoji} {card}\n\n"
                f"⚽ {home_name} vs {away_name}\n\n"
                f"👤 {player['name']}\n"
                f"⏱️ {minute}"
            )

            send_telegram(message)

            print(
                f"  📱 Card notification sent: "
                f"{player['name']} — {card}"
            )

            reported.append(
                event_key
            )

            continue

        # ----------------------------------------------------
        # SUBSTITUTION
        # ----------------------------------------------------

        if event_type == "substitution":

            player_id = get_event_player_id(
                event
            )

            swap_players = get_swap_players(
                event
            )

            involved_ids = set()

            if player_id is not None:
                involved_ids.add(player_id)

            for swap_player in swap_players:
                if swap_player["id"] is not None:
                    involved_ids.add(
                        swap_player["id"]
                    )

            tracked_involved = [
                player_lookup[player_id]
                for player_id in involved_ids
                if player_id in player_lookup
            ]

            if not tracked_involved:
                continue

            player_in, player_out = determine_substitution(
                event,
                substitution_info
            )

            if player_in and player_out:
                message = (
                    "🔄 SUBSTITUTION\n\n"
                    f"⚽ {home_name} vs {away_name}\n\n"
                    f"➡️ IN: {player_in}\n"
                    f"⬅️ OUT: {player_out}\n"
                    f"⏱️ {minute}"
                )
            else:
                names = [
                    player.get(
                        "name",
                        "Unknown"
                    )
                    for player in tracked_involved
                ]

                message = (
                    "🔄 SUBSTITUTION\n\n"
                    f"⚽ {home_name} vs {away_name}\n\n"
                    f"👤 {' / '.join(names)}\n"
                    f"⏱️ {minute}"
                )

            send_telegram(message)

            print(
                "  📱 Substitution notification sent."
            )

            reported.append(
                event_key
            )

    # --------------------------------------------------------
    # PENALTY MISSES FROM SHOTMAP
    # --------------------------------------------------------

    shotmap = content.get(
        "shotmap"
    ) or {}

    shots = shotmap.get(
        "shots"
    ) or []

    for shot in shots:

        if not isinstance(shot, dict):
            continue

        event_type_text = " ".join([
            str(shot.get("eventType", "")),
            str(shot.get("shotType", "")),
            str(shot.get("situation", "")),
        ]).lower()

        if "penalty" not in event_type_text:
            continue

        if (
            "scored" in event_type_text
            or "goal" in event_type_text
        ):
            continue

        if not any(
            term in event_type_text
            for term in [
                "miss",
                "saved",
                "save",
                "off target",
            ]
        ):
            continue

        player_id = shot.get(
            "playerId"
        )

        try:
            player_id = int(player_id)
        except (
            TypeError,
            ValueError
        ):
            continue

        if player_id not in player_lookup:
            continue

        minute_value = (
            shot.get("min")
            if shot.get("min") is not None
            else shot.get("minute")
        )

        penalty_key = (
            f"penalty-missed|"
            f"{player_id}|"
            f"{minute_value}"
        )

        if penalty_key in reported:
            continue

        player = player_lookup[
            player_id
        ]

        minute_text = (
            f"{minute_value}'"
            if minute_value is not None
            else ""
        )

        message = (
            "❌ PENALTY MISSED\n\n"
            f"⚽ {home_name} vs {away_name}\n\n"
            f"👤 {player['name']}\n"
            f"⏱️ {minute_text}"
        )

        send_telegram(message)

        print(
            f"  📱 Missed-penalty notification sent: "
            f"{player['name']}"
        )

        reported.append(
            penalty_key
        )



# ============================================================
# PLAYER FINAL STATS
# ============================================================

def normalize_stat_key(value):

    if value is None:
        return ""

    text = str(
        value
    ).strip().lower()

    replacements = {
        "_": " ",
        "-": " ",
        ",": " ",
        ".": " ",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    return " ".join(
        text.split()
    )


def extract_scalar_stat(value):
    """
    Convert FotMob's nested stat values into a printable value.
    Handles:
      - scalar numbers/strings
      - {value: X, total: Y} -> X/Y
      - {num: X}
      - {stat: {...}}
    """

    if value is None:
        return None

    if isinstance(
        value,
        (str, int, float, bool)
    ):
        return value

    if isinstance(
        value,
        list
    ):
        if len(value) == 2:
            left = extract_scalar_stat(
                value[0]
            )
            right = extract_scalar_stat(
                value[1]
            )

            if (
                left is not None
                and right is not None
            ):
                return f"{left}/{right}"

        return None

    if isinstance(
        value,
        dict
    ):

        if (
            "value" in value
            and "total" in value
        ):
            left = extract_scalar_stat(
                value.get("value")
            )
            right = extract_scalar_stat(
                value.get("total")
            )

            if (
                left is not None
                and right is not None
            ):
                return f"{left}/{right}"

        for key in [
            "value",
            "num",
            "displayValue",
            "formattedValue",
            "text",
        ]:
            if key in value:
                result = extract_scalar_stat(
                    value.get(key)
                )

                if result is not None:
                    return result

        nested = value.get(
            "stat"
        )

        if nested is not None:
            return extract_scalar_stat(
                nested
            )

    return None


def extract_player_stat_rows(
    player_data
):
    """
    Extract all scalar player statistics available in FotMob's
    current matchDetails playerStats structure.
    """

    rows = []
    seen = set()

    def add_row(label, value):
        if not label:
            return

        printable = extract_scalar_stat(
            value
        )

        if printable is None:
            return

        key = normalize_stat_key(
            label
        )

        if not key or key in seen:
            return

        seen.add(key)

        rows.append(
            (
                str(label),
                printable,
            )
        )

    stats_blob = player_data.get(
        "stats"
    )

    if isinstance(
        stats_blob,
        list
    ):

        for group in stats_blob:

            if not isinstance(
                group,
                dict
            ):
                continue

            group_stats = group.get(
                "stats"
            )

            if isinstance(
                group_stats,
                dict
            ):

                for label, value in (
                    group_stats.items()
                ):
                    add_row(
                        label,
                        value
                    )

            elif group_stats is not None:

                label = (
                    group.get(
                        "title"
                    )
                    or group.get(
                        "key"
                    )
                )

                add_row(
                    label,
                    group_stats
                )

    elif isinstance(
        stats_blob,
        dict
    ):

        for label, value in (
            stats_blob.items()
        ):
            add_row(
                label,
                value
            )

    # Some FotMob payload variants expose these directly.
    direct_fields = {
        "FotMob rating": player_data.get(
            "rating"
        ),
        "Minutes played": player_data.get(
            "minutesPlayed"
        ),
        "Goals": player_data.get(
            "goals"
        ),
        "Assists": player_data.get(
            "assists"
        ),
        "Player rating": player_data.get(
            "playerRating"
        ),
        "Minutes": player_data.get(
            "minsPlayed"
        ),
    }

    for label, value in (
        direct_fields.items()
    ):
        add_row(
            label,
            value
        )

    return rows


def get_stat_from_rows(
    rows,
    aliases,
):
    wanted = {
        normalize_stat_key(
            alias
        )
        for alias in aliases
    }

    for label, value in rows:

        if (
            normalize_stat_key(label)
            in wanted
        ):
            return value

    return None


def get_lineup_player_data(details):
    """
    Map player ID -> lineup player object, so we can use
    lineup performance/minutes as a fallback.
    """

    lineup = (
        details.get(
            "content",
            {}
        ).get(
            "lineup"
        )
        or {}
    )

    result = {}

    for side_key in [
        "homeTeam",
        "awayTeam",
    ]:

        side = lineup.get(
            side_key
        )

        if not side:
            continue

        for role in [
            "starters",
            "subs",
        ]:

            for player in side.get(
                role,
                []
            ):

                player_id = player.get(
                    "id"
                )

                if player_id is None:
                    continue

                try:
                    player_id = int(
                        player_id
                    )
                except (
                    TypeError,
                    ValueError
                ):
                    continue

                result[player_id] = player

    return result



def get_played_tracked_player_ids(
    details,
    tracked_player_ids,
):
    """
    Return tracked players who are known to have actually played.

    Returns:
      - set(...) when lineup data is available
      - None when lineup data is unavailable, so the caller can retry
    """

    lineup = (
        details.get(
            "content",
            {}
        ).get(
            "lineup"
        )
    )

    if not lineup:
        return None

    result = set()

    tracked_ids = {
        int(player_id)
        for player_id in tracked_player_ids
    }

    for side_key in [
        "homeTeam",
        "awayTeam",
    ]:

        side = lineup.get(
            side_key
        )

        if not side:
            continue

        for role in [
            "starters",
            "subs",
        ]:

            for player in side.get(
                role,
                []
            ):

                player_id = player.get(
                    "id"
                )

                if player_id is None:
                    continue

                try:
                    player_id = int(
                        player_id
                    )
                except (
                    TypeError,
                    ValueError
                ):
                    continue

                if player_id not in tracked_ids:
                    continue

                if role == "starters":
                    # A starter necessarily appeared in the match,
                    # even if later substituted off.
                    result.add(player_id)
                    continue

                # Bench player: only count them once there is evidence
                # they entered the match.
                events = (
                    player.get(
                        "events"
                    )
                    or {}
                )

                sub = (
                    events.get(
                        "sub"
                    )
                    or {}
                )

                time_subbed_on = player.get(
                    "timeSubbedOn"
                )

                subbed_in = sub.get(
                    "subbedIn"
                )

                performance = (
                    player.get(
                        "performance"
                    )
                    or {}
                )

                minutes_played = (
                    player.get(
                        "minutesPlayed"
                    )
                )

                if (
                    time_subbed_on is not None
                    or subbed_in is not None
                    or (
                        minutes_played is not None
                        and str(minutes_played) not in {
                            "0",
                            "0.0",
                        }
                    )
                    or performance
                ):
                    result.add(player_id)

    return result


def get_player_match_stats(
    details,
    player_lookup,
):

    content = details.get(
        "content",
        {}
    )

    player_stats = (
        content.get(
            "playerStats"
        )
        or {}
    )

    results = {}

    if not isinstance(
        player_stats,
        dict
    ):
        return results

    lineup_players = (
        get_lineup_player_data(
            details
        )
    )

    for player_id_raw, data in (
        player_stats.items()
    ):

        if not isinstance(
            data,
            dict
        ):
            continue

        player_id = data.get(
            "id"
        )

        if player_id is None:
            player_id = data.get(
                "playerId"
            )

        if player_id is None:
            player_id = player_id_raw

        try:
            player_id = int(
                player_id
            )
        except (
            TypeError,
            ValueError
        ):
            continue

        if player_id not in player_lookup:
            continue

        rows = extract_player_stat_rows(
            data
        )

        lineup_data = lineup_players.get(
            player_id,
            {}
        )

        performance = (
            lineup_data.get(
                "performance"
            )
            or {}
        )

        lineup_rating = None

        if isinstance(
            performance,
            dict
        ):
            lineup_rating = performance.get(
                "rating"
            )

        if lineup_rating is None:
            lineup_rating = extract_scalar_stat(
                lineup_data.get(
                    "rating"
                )
            )

        lineup_minutes = extract_scalar_stat(
            lineup_data.get(
                "minutesPlayed"
            )
        )

        direct_minutes = extract_scalar_stat(
            data.get(
                "minutesPlayed"
            )
        )

        direct_rating = extract_scalar_stat(
            data.get(
                "rating"
            )
        )

        minutes = (
            direct_minutes
            or get_stat_from_rows(
                rows,
                [
                    "Minutes played",
                    "minutes played",
                    "minutesPlayed",
                    "Mins played",
                    "minsPlayed",
                ],
            )
            or lineup_minutes
        )

        rating = (
            direct_rating
            or get_stat_from_rows(
                rows,
                [
                    "FotMob rating",
                    "Player rating",
                    "rating",
                    "playerRating",
                ],
            )
            or lineup_rating
        )

        name = (
            data.get(
                "name"
            )
            or data.get(
                "fullName"
            )
            or player_lookup[
                player_id
            ]["name"]
        )

        # Bench players who never played are normally represented
        # with empty stats. Keep them out of final reports.
        if (
            not rows
            and minutes is None
            and rating is None
        ):
            continue

        results[player_id] = {
            "name": name,
            "rows": rows,
            "minutes": minutes,
            "rating": rating,
        }

    return results


STAT_GROUPS = [
    (
        "⚽ Attacking",
        [
            (
                "Goals",
                ["Goals"]
            ),
            (
                "Assists",
                [
                    "Assists",
                    "Goal assist",
                    "goalAssist",
                ]
            ),
            (
                "Total shots",
                [
                    "Total shots",
                    "total shots",
                    "totalScoringAtt",
                ]
            ),
            (
                "Shots on target",
                [
                    "Shots on target",
                    "ontarget scoring att",
                    "ontargetScoringAtt",
                ]
            ),
            (
                "Expected goals (xG)",
                [
                    "Expected goals (xG)",
                    "Expected goals",
                    "expectedGoals",
                ]
            ),
            (
                "Expected assists (xA)",
                [
                    "Expected assists (xA)",
                    "Expected assists",
                ]
            ),
            (
                "xG + xA",
                ["xG + xA"]
            ),
            (
                "Chances created",
                ["Chances created"]
            ),
            (
                "Big chances missed",
                ["Big chances missed"]
            ),
            (
                "Touches in opposition box",
                [
                    "Touches in opposition box",
                    "Touches opp box",
                ]
            ),
            (
                "Offsides",
                ["Offsides"]
            ),
        ],
    ),
    (
        "🎯 Passing",
        [
            (
                "Accurate passes",
                ["Accurate passes"]
            ),
            (
                "Accurate long balls",
                ["Accurate long balls"]
            ),
            (
                "Accurate crosses",
                ["Accurate crosses"]
            ),
            (
                "Passes into final third",
                ["Passes into final third"]
            ),
            (
                "Corners",
                ["Corners"]
            ),
        ],
    ),
    (
        "🛡️ Defending",
        [
            (
                "Tackles won",
                ["Tackles won"]
            ),
            (
                "Interceptions",
                ["Interceptions"]
            ),
            (
                "Clearances",
                ["Clearances"]
            ),
            (
                "Defensive actions",
                ["Defensive actions"]
            ),
            (
                "Blocks",
                ["Blocks"]
            ),
            (
                "Duels won",
                ["Duels won"]
            ),
            (
                "Duels lost",
                ["Duels lost"]
            ),
            (
                "Ground duels won",
                ["Ground duels won"]
            ),
            (
                "Aerial duels won",
                ["Aerial duels won"]
            ),
            (
                "Dribbled past",
                ["Dribbled past"]
            ),
            (
                "Recoveries",
                ["Recoveries"]
            ),
        ],
    ),
    (
        "🧤 Goalkeeping",
        [
            (
                "Saves",
                ["Saves"]
            ),
            (
                "Goals conceded",
                ["Goals conceded"]
            ),
            (
                "Goals prevented",
                ["Goals prevented"]
            ),
            (
                "xGOT faced",
                ["xGOT faced"]
            ),
        ],
    ),
    (
        "📋 Other",
        [
            (
                "Touches",
                ["Touches"]
            ),
            (
                "Successful dribbles",
                ["Successful dribbles"]
            ),
            (
                "Was fouled",
                ["Was fouled"]
            ),
            (
                "Fouls committed",
                [
                    "Fouls committed",
                    "Fouls",
                ]
            ),
            (
                "Dispossessed",
                ["Dispossessed"]
            ),
            (
                "Yellow card",
                ["Yellow card"]
            ),
            (
                "Red card",
                ["Red card"]
            ),
            (
                "Shot accuracy",
                ["Shot accuracy"]
            ),
            (
                "Fantasy points",
                ["Fantasy points"]
            ),
        ],
    ),
]


def format_player_stat_block(
    stats
):
    rows = stats.get(
        "rows",
        []
    )

    if not rows:
        return ""

    used = set()
    parts = []

    for group_name, items in (
        STAT_GROUPS
    ):

        lines = []

        for display_name, aliases in items:

            value = get_stat_from_rows(
                rows,
                aliases,
            )

            if value is None:
                continue

            lines.append(
                f"• {display_name}: {value}"
            )

            for alias in aliases:
                used.add(
                    normalize_stat_key(
                        alias
                    )
                )

        if lines:
            parts.append(
                group_name
                + "\n"
                + "\n".join(lines)
            )

    excluded = {
        "name",
        "position",
        "position string short",
        "localized position",
        "shirt",
        "usual position",
        "team id",
        "image url",
        "page url",
        "is home team",
        "is captain",
        "rating",
        "fotmob rating",
        "minutes played",
        "fantasy score",
        "shotmap",
        "team data",
        "role",
        "player rating",
        "playerid",
        "player id",
    }

    remaining = []

    for label, value in rows:

        normalized = normalize_stat_key(
            label
        )

        if normalized in used:
            continue

        if normalized in excluded:
            continue

        remaining.append(
            f"• {label}: {value}"
        )

    if remaining:
        parts.append(
            "📌 Additional"
            + "\n"
            + "\n".join(remaining)
        )

    return "\n\n".join(parts)


def process_final_report(
    match,
    details,
    state,
    player_lookup,
    tracked_player_ids=None,
):

    match_id = str(
        match["id"]
    )

    status = (
        details.get(
            "header",
            {}
        ).get(
            "status"
        )
        or {}
    )

    if not status.get(
        "finished"
    ):
        return False

    if status.get(
        "cancelled"
    ):
        print(
            "  ⚠️ Match was cancelled; "
            "no final report."
        )
        return True

    if tracked_player_ids is None:
        tracked_player_ids = (
            get_tracked_player_ids_for_match(
                match,
                player_lookup,
            )
        )

    tracked_player_ids = {
        int(player_id)
        for player_id in tracked_player_ids
    }

    player_stats = get_player_match_stats(
        details,
        player_lookup,
    )

    candidate_ids = {
        player_id
        for player_id in player_stats
        if player_id in tracked_player_ids
    }

    played_ids_from_lineup = (
        get_played_tracked_player_ids(
            details,
            tracked_player_ids,
        )
    )

    reported = (
        state[
            "final_posts"
        ].setdefault(
            match_id,
            []
        )
    )

    home_name = (
        match.get(
            "home",
            {}
        ).get(
            "name",
            "Home"
        )
    )

    away_name = (
        match.get(
            "away",
            {}
        ).get(
            "name",
            "Away"
        )
    )

    score_str = (
        status.get(
            "scoreStr"
        )
        or ""
    )

    reason = (
        status.get(
            "reason",
            {}
        ).get(
            "long"
        )
        or "Full-Time"
    )

    for player_id in sorted(
        candidate_ids
    ):

        stats = player_stats[
            player_id
        ]

        report_key = str(
            player_id
        )

        if report_key in reported:

            print(
                f"  ↪ Final report already sent: "
                f"{stats['name']}"
            )

            continue

        minutes = stats.get(
            "minutes"
        )

        rating = stats.get(
            "rating"
        )

        message = (
            "🏁 FULL TIME\n\n"
            f"⚽ {home_name} "
            f"{score_str} "
            f"{away_name}\n"
            f"📌 {reason}\n\n"
            f"👤 {stats['name']}\n"
        )

        if minutes is not None:
            message += (
                f"⏱️ {minutes} min\n"
            )

        if rating is not None:
            message += (
                f"⭐ FotMob rating: "
                f"{rating}\n"
            )

        performance_block = (
            format_player_stat_block(
                stats
            )
        )

        if performance_block:
            message += (
                "\n📊 PLAYER PERFORMANCE\n"
                + performance_block
            )

        if len(message) > 3900:
            message = (
                message[:3850]
                + "\n\n…some additional FotMob statistics were omitted."
            )

        send_telegram(
            message
        )

        print(
            f"  📱 Final report sent: "
            f"{stats['name']}"
        )

        reported.append(
            report_key
        )

    # If playerStats has tracked players, all of them need reports.
    if candidate_ids:
        return all(
            str(player_id) in reported
            for player_id in candidate_ids
        )

    # If the confirmed lineup shows no tracked player played,
    # there is nothing to publish.
    if (
        played_ids_from_lineup
        == set()
        and played_ids_from_lineup is not None
    ):
        return True

    # Stats may simply not be ready yet. Keep the match alive.
    return False



# ============================================================
# PERSISTENT MATCH MONITORING
# ============================================================

MONITORED_MATCH_MAX_AGE_HOURS = 48


def get_tracked_player_ids_for_match(
    match,
    player_lookup,
):

    home_id = (
        match.get(
            "home",
            {}
        ).get(
            "id"
        )
    )

    away_id = (
        match.get(
            "away",
            {}
        ).get(
            "id"
        )
    )

    result = []

    for player_id, player in player_lookup.items():

        club_id = player.get(
            "team_id"
        )

        national_id = player.get(
            "national_team_id"
        )

        monitor_national = player.get(
            "monitor_national_team",
            True
        )

        matched = False

        try:
            if club_id is not None:
                club_id = int(club_id)

                if (
                    home_id is not None
                    and int(home_id) == club_id
                ):
                    matched = True

                elif (
                    away_id is not None
                    and int(away_id) == club_id
                ):
                    matched = True

        except (
            TypeError,
            ValueError
        ):
            pass

        if (
            not matched
            and monitor_national
            and national_id is not None
        ):

            try:
                national_id = int(
                    national_id
                )

                if (
                    home_id is not None
                    and int(home_id) == national_id
                ):
                    matched = True

                elif (
                    away_id is not None
                    and int(away_id) == national_id
                ):
                    matched = True

            except (
                TypeError,
                ValueError
            ):
                pass

        if matched:
            result.append(
                int(player_id)
            )

    return result


def register_monitored_match(
    match,
    state,
    player_lookup,
):

    state.setdefault(
        "monitored_matches",
        {}
    )

    match_id = str(
        match["id"]
    )

    now = get_local_now()

    tracked_ids = (
        get_tracked_player_ids_for_match(
            match,
            player_lookup,
        )
    )

    entry = state[
        "monitored_matches"
    ].get(
        match_id
    )

    if entry is None:

        entry = {
            "match": match,
            "tracked_player_ids": tracked_ids,
            "discovered_at": now.isoformat(),
            "finished_seen_at": None,
            "next_check_at": now.isoformat(),
            "final_complete": False,
        }

        state[
            "monitored_matches"
        ][match_id] = entry

    else:

        entry["match"] = match

        existing = {
            int(player_id)
            for player_id in entry.get(
                "tracked_player_ids",
                []
            )
        }

        existing.update(
            tracked_ids
        )

        entry[
            "tracked_player_ids"
        ] = sorted(
            existing
        )

    return entry


def should_process_monitored_match(
    entry,
    now,
):

    next_check_at = parse_iso_datetime(
        entry.get(
            "next_check_at"
        )
    )

    if next_check_at is None:
        return True

    return now >= (
        next_check_at.astimezone(
            LOCAL_TIMEZONE
        )
    )


def schedule_next_match_check(
    entry,
    now,
    finished,
):

    if not finished:
        # Current/live matches should be checked every scheduler tick.
        entry[
            "next_check_at"
        ] = now.isoformat()
        return

    finished_seen_at = parse_iso_datetime(
        entry.get(
            "finished_seen_at"
        )
    )

    if finished_seen_at is None:
        finished_seen_at = now

        entry[
            "finished_seen_at"
        ] = now.isoformat()

    elapsed_minutes = (
        now
        - finished_seen_at.astimezone(
            LOCAL_TIMEZONE
        )
    ).total_seconds() / 60

    if elapsed_minutes < 20:
        delay_minutes = 1
    elif elapsed_minutes < 120:
        delay_minutes = 5
    elif elapsed_minutes < 720:
        delay_minutes = 15
    else:
        delay_minutes = 60

    entry[
        "next_check_at"
    ] = (
        now
        + timedelta(
            minutes=delay_minutes
        )
    ).isoformat()


def prune_monitored_matches(
    state,
    now,
):

    monitored = state.get(
        "monitored_matches",
        {}
    )

    remove_ids = []

    for match_id, entry in monitored.items():

        if entry.get(
            "final_complete"
        ):
            remove_ids.append(
                match_id
            )
            continue

        match = entry.get(
            "match"
        ) or {}

        kickoff = parse_match_kickoff(
            match
        )

        if kickoff is None:

            discovered_at = (
                parse_iso_datetime(
                    entry.get(
                        "discovered_at"
                    )
                )
            )

            if discovered_at is None:
                continue

            age_hours = (
                now
                - discovered_at.astimezone(
                    LOCAL_TIMEZONE
                )
            ).total_seconds() / 3600

        else:

            age_hours = (
                now
                - kickoff
            ).total_seconds() / 3600

        # Keep remembered matches long enough to survive
        # fixture-feed removal and delayed final statistics.
        if age_hours > MONITORED_MATCH_MAX_AGE_HOURS:
            remove_ids.append(
                match_id
            )

    for match_id in remove_ids:
        monitored.pop(
            match_id,
            None
        )


def build_matches_to_process(
    relevant_matches,
    state,
    now,
):

    matches_to_process = {}

    # Current daily fixture results always get checked.
    for match in relevant_matches:

        match_id = str(
            match.get("id")
        )

        matches_to_process[
            match_id
        ] = match

    # Remembered matches continue to be checked even after
    # they disappear from /matches.
    for match_id, entry in (
        state.get(
            "monitored_matches",
            {}
        ).items()
    ):

        if match_id in matches_to_process:
            continue

        if not should_process_monitored_match(
            entry,
            now,
        ):
            continue

        remembered_match = entry.get(
            "match"
        )

        if remembered_match:
            matches_to_process[
                str(match_id)
            ] = remembered_match

    ordered = list(
        matches_to_process.items()
    )

    ordered.sort(
        key=lambda item: (
            parse_match_kickoff(
                item[1]
            )
            or now
        )
    )

    return ordered

# ============================================================
# TRANSFER MONITORING
# ============================================================

# ============================================================
# TRANSFER MONITORING
# ============================================================

TRANSFER_CHECK_INTERVAL_MINUTES = 30
TRANSFER_PAGES_TO_SCAN = 3


def parse_iso_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00"
            )
        )
    except ValueError:
        return None


def get_transfer_key(transfer):
    return "|".join([
        str(transfer.get("playerId", "")),
        str(transfer.get("transferDate", "")),
        str(transfer.get("fromClubId", "")),
        str(transfer.get("toClubId", "")),
        str(transfer.get("transferType", {}).get("text", "")),
    ])


def get_transfer_label(transfer):
    transfer_type = transfer.get(
        "transferType"
    ) or {}

    text = (
        transfer_type.get("text")
        or transfer.get("fee", {}).get("feeText")
        or "transfer"
    )

    if transfer.get("onLoan"):
        return "LOAN"

    return str(text).upper()


def format_transfer_date(transfer):
    date_value = transfer.get(
        "transferDate"
    )

    parsed = parse_iso_datetime(
        date_value
    )

    if parsed is None:
        return None

    return parsed.astimezone(
        LOCAL_TIMEZONE
    ).strftime(
        "%d %b %Y"
    )


def update_player_after_transfer(
    player,
    transfer,
):
    """Update the tracked player's club snapshot."""

    to_club_id = transfer.get(
        "toClubId"
    )

    to_club_name = transfer.get(
        "toClub"
    )

    if to_club_id is not None:
        try:
            player["team_id"] = int(
                to_club_id
            )
        except (
            TypeError,
            ValueError
        ):
            player["team_id"] = to_club_id

    if to_club_name:
        player["team_name"] = to_club_name

    player["on_loan"] = bool(
        transfer.get("onLoan")
    )


def process_transfer_monitoring(
    players,
    state,
):
    """
    Check FotMob's transfer center periodically.

    The bot runs every few minutes, but transfers do not need
    a request on every run. We therefore check every 30 minutes.
    """

    monitor = state.setdefault(
        "transfer_monitor",
        {
            "initialized": False,
            "last_checked": None,
            "seen": [],
        },
    )

    now = get_local_now()

    last_checked = parse_iso_datetime(
        monitor.get("last_checked")
    )

    if last_checked is not None:
        elapsed = (
            now - last_checked.astimezone(
                LOCAL_TIMEZONE
            )
        ).total_seconds()

        if elapsed < (
            TRANSFER_CHECK_INTERVAL_MINUTES * 60
        ):
            print(
                "  ↪ Transfer check not due yet "
                f"({TRANSFER_CHECK_INTERVAL_MINUTES} min interval)."
            )
            return False

    player_lookup = {
        int(player["fotmob_id"]): player
        for player in players
        if player.get("fotmob_id") is not None
    }

    print(
        "  🔄 Checking FotMob transfer center..."
    )

    transfers = []

    try:
        for page in range(
            1,
            TRANSFER_PAGES_TO_SCAN + 1,
        ):
            data = fotmob_get(
                "transfers",
                {
                    "page": page,
                    "showLoans": "true",
                },
            )

            page_transfers = data.get(
                "transfers",
                []
            )

            if not isinstance(
                page_transfers,
                list
            ):
                break

            transfers.extend(
                page_transfers
            )

            if not page_transfers:
                break

    except Exception as e:
        print(
            "  ⚠️ Transfer check failed: "
            f"{e}"
        )
        return False

    if not transfers:
        monitor["last_checked"] = now.isoformat()

        print(
            "  ℹ️ No transfer records returned."
        )

        return True

    seen = set(
        monitor.get("seen", [])
    )

    # --------------------------------------------------------
    # First run: seed the transfer list without sending a huge
    # batch of historical notifications.
    # --------------------------------------------------------

    if not monitor.get(
        "initialized",
        False
    ):
        for transfer in transfers:
            seen.add(
                get_transfer_key(
                    transfer
                )
            )

        monitor["seen"] = list(seen)[-1000:]
        monitor["last_checked"] = now.isoformat()
        monitor["initialized"] = True

        print(
            f"  ✅ Transfer monitor initialized "
            f"({len(transfers)} recent records marked as seen)."
        )

        return True

    tracked_changes = []

    for transfer in transfers:

        player_id = transfer.get(
            "playerId"
        )

        try:
            player_id = int(
                player_id
            )
        except (
            TypeError,
            ValueError
        ):
            continue

        if player_id not in player_lookup:
            continue

        transfer_key = get_transfer_key(
            transfer
        )

        if transfer_key in seen:
            continue

        player = player_lookup[
            player_id
        ]

        tracked_changes.append(
            (
                player,
                transfer,
                transfer_key,
            )
        )

    for (
        player,
        transfer,
        transfer_key,
    ) in tracked_changes:

        transfer_label = get_transfer_label(
            transfer
        )

        from_club = (
            transfer.get(
                "fromClub"
            )
            or "Unknown"
        )

        to_club = (
            transfer.get(
                "toClub"
            )
            or "Unknown"
        )

        date_text = format_transfer_date(
            transfer
        )

        if transfer_label == "LOAN":
            title = "🔄 LOAN"
        else:
            title = "🔄 TRANSFER"

        message = (
            f"{title}\n\n"
            f"👤 {player['name']}\n"
            f"➡️ {from_club} → {to_club}"
        )

        if date_text:
            message += (
                f"\n📅 {date_text}"
            )

        fee = (
            transfer.get("fee", {})
            if isinstance(
                transfer.get("fee"),
                dict
            )
            else {}
        )

        fee_text = (
            fee.get("feeText")
            or transfer.get(
                "transferType",
                {}
            ).get("text")
        )

        if fee_text and str(fee_text).lower() not in {
            "on loan",
            "loan",
        }:
            message += (
                f"\n💰 {fee_text}"
            )

        send_telegram(
            message
        )

        print(
            f"  📱 Transfer notification sent: "
            f"{player['name']} — "
            f"{from_club} → {to_club}"
        )

        update_player_after_transfer(
            player,
            transfer
        )

        seen.add(
            transfer_key
        )

    monitor["seen"] = list(seen)[-1000:]
    monitor["last_checked"] = now.isoformat()

    return bool(tracked_changes)



# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("BARCELONA PLAYER BOT")
    print("=" * 70)

    players_data = load_json(
        PLAYERS_FILE,
        [],
    )

    if isinstance(
        players_data,
        dict
    ):
        players = players_data.get(
            "players",
            []
        )
    else:
        players = players_data

    state = load_json(
        STATE_FILE,
        {
            "daily_posts": [],
            "lineup_notifications": {},
            "match_events": {},
            "final_posts": {},
        },
    )

    state.setdefault(
        "daily_posts",
        []
    )

    state.setdefault(
        "lineup_notifications",
        {}
    )

    state.setdefault(
        "match_events",
        {}
    )

    state.setdefault(
        "final_posts",
        {}
    )

    state.setdefault(
        "transfer_monitor",
        {
            "initialized": False,
            "last_checked": None,
            "seen": [],
        }
    )

    state.setdefault(
        "monitored_matches",
        {}
    )

    # --------------------------------------------------------
    # TRANSFERS / LOANS
    # --------------------------------------------------------

    process_transfer_monitoring(
        players,
        state,
    )

    # Rebuild lookup after a transfer/loan may have changed
    # a tracked player's current club.
    player_lookup = (
        build_player_lookup(
            players
        )
    )

    tracked_teams = (
        build_tracked_teams(
            players
        )
    )

    print(
        f"Tracking {len(players)} players"
    )

    print(
        f"Tracking {len(tracked_teams)} "
        f"club/national teams"
    )

    now = get_local_now()

    # ========================================================
    # CURRENT MATCH DISCOVERY
    # ========================================================

    today = now.date()

    print(
        f"Checking tracked matches "
        f"for {today}..."
    )

    leagues = get_today_matches()

    matches = collect_matches(
        leagues
    )

    relevant_matches = [
        match
        for match in matches
        if is_relevant_match(
            match,
            tracked_teams,
        )
    ]

    print(
        f"Found {len(relevant_matches)} "
        f"relevant matches."
    )

    # Remember every relevant match before processing it.
    # This is the key fix for post-game reporting.
    for match in relevant_matches:
        register_monitored_match(
            match,
            state,
            player_lookup,
        )

    # ========================================================
    # DAILY MATCHES POST
    # ========================================================

    (
        daily_window_start,
        daily_window_end,
        now,
    ) = get_daily_window()

    print(
        "Daily Matches window:"
    )

    print(
        f"  {daily_window_start.strftime('%Y-%m-%d %H:%M')}"
        f" -> "
        f"{daily_window_end.strftime('%Y-%m-%d %H:%M')}"
        f" Tehran"
    )

    if now >= daily_window_start:

        daily_matches = (
            get_daily_window_matches(
                daily_window_start,
                daily_window_end,
            )
        )

        daily_relevant_matches = [
            match
            for match in daily_matches
            if is_relevant_match(
                match,
                tracked_teams,
            )
        ]

        print(
            f"Found {len(daily_relevant_matches)} "
            f"relevant matches in Daily Matches window."
        )

        process_daily_schedule(
            daily_relevant_matches,
            state,
            player_lookup,
            daily_window_start,
            daily_window_end,
        )

    else:

        print(
            "  ⏳ Daily Matches post is not due yet."
        )

        print(
            f"  It will be due at "
            f"{daily_window_start.strftime('%Y-%m-%d %H:%M')} "
            f"Tehran."
        )

    print("=" * 70)

    # ========================================================
    # CURRENT + PERSISTENT MATCH PROCESSING
    # ========================================================

    matches_to_process = build_matches_to_process(
        relevant_matches,
        state,
        now,
    )

    print(
        f"Processing {len(matches_to_process)} "
        f"current/remembered matches."
    )

    print("=" * 70)

    for match_id, match in matches_to_process:

        entry = state[
            "monitored_matches"
        ].get(
            str(match_id)
        )

        if entry is None:
            entry = register_monitored_match(
                match,
                state,
                player_lookup,
            )

        home_name = (
            match.get(
                "home",
                {}
            ).get(
                "name",
                "Home"
            )
        )

        away_name = (
            match.get(
                "away",
                {}
            ).get(
                "name",
                "Away"
            )
        )

        is_current_match = (
            str(match_id)
            in {
                str(match.get("id"))
                for match in relevant_matches
            }
        )

        label = (
            ""
            if is_current_match
            else " (remembered match)"
        )

        print(
            f"Checking: "
            f"{home_name} vs "
            f"{away_name}"
            f"{label}"
        )

        try:

            details = (
                get_match_details(
                    match_id
                )
            )

            status = (
                details.get(
                    "header",
                    {}
                ).get(
                    "status"
                )
                or {}
            )

            # ------------------------------------------------
            # CONFIRMED LINEUP
            # ------------------------------------------------

            process_confirmed_lineup(
                match,
                details,
                state,
                player_lookup,
            )

            # ------------------------------------------------
            # LIVE EVENTS
            # ------------------------------------------------

            process_match_events(
                match,
                details,
                state,
                player_lookup,
            )

            # ------------------------------------------------
            # FINAL REPORT
            # ------------------------------------------------

            final_complete = process_final_report(
                match,
                details,
                state,
                player_lookup,
                entry.get(
                    "tracked_player_ids",
                    [],
                ),
            )

            finished = bool(
                status.get(
                    "finished"
                )
            )

            if finished:

                if final_complete:

                    entry[
                        "final_complete"
                    ] = True

                    print(
                        "  ✅ Post-game monitoring complete."
                    )

                else:

                    schedule_next_match_check(
                        entry,
                        now,
                        True,
                    )

                    print(
                        "  ⏳ Final statistics are not complete yet; "
                        "match remains monitored."
                    )

            else:

                schedule_next_match_check(
                    entry,
                    now,
                    False,
                )

        except Exception as e:

            print(
                f"  ❌ Error processing match "
                f"{match_id}: {e}"
            )

    # Remove completed/expired remembered matches.
    prune_monitored_matches(
        state,
        now,
    )

    # ========================================================
    # SAVE
    # ========================================================

    save_json(
        STATE_FILE,
        state,
    )

    # Persist any club changes from transfer/loan detection.
    existing_players = load_json(
        PLAYERS_FILE,
        None
    )

    if existing_players != players:

        save_json(
            PLAYERS_FILE,
            players
        )

        print(
            "💾 Updated players_resolved.json "
            "after transfer/loan change."
        )

    print(
        "💾 Bot state updated."
    )

    print("=" * 70)

    print(
        "LINEUP + LIVE EVENT + DAILY MATCHES + "
        "TRANSFER + PERSISTENT MATCH + "
        "FINAL REPORT MONITORING COMPLETE"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
