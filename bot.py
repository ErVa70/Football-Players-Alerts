import json
import os
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


def get_assist_name(event):

    assist = event.get(
        "assist"
    )

    if isinstance(
        assist,
        dict
    ):
        return (
            assist.get(
                "name"
            )
            or assist.get(
                "playerName"
            )
            or assist.get(
                "fullName"
            )
        )

    if isinstance(
        assist,
        str
    ):
        return assist

    return (
        event.get(
            "assistName"
        )
        or event.get(
            "assistPlayerName"
        )
    )


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

def process_match_events(
    match,
    details,
    state,
    player_lookup,
):

    match_id = str(
        match["id"]
    )

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

    started = bool(
        status.get(
            "started"
        )
    )

    finished = bool(
        status.get(
            "finished"
        )
    )

    if not started:
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

    if not events:
        return

    reported = (
        state[
            "match_events"
        ].setdefault(
            match_id,
            []
        )
    )

    # Do not backfill all old live events
    # when a finished match is first encountered.
    if finished and not reported:

        state[
            "match_events"
        ][match_id] = [
            get_event_key(event)
            for event in events
        ]

        print(
            "  ℹ️ Match already finished; "
            "existing events marked as seen."
        )

        return

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

        event_key = get_event_key(
            event
        )

        if event_key in reported:
            continue

        event_type = str(
            event.get(
                "type",
                ""
            )
        ).strip().lower()

        minute = get_minute(
            event
        )

        # ----------------------------------------------------
        # GOAL
        # ----------------------------------------------------

        if event_type == "goal":

            player_id = (
                get_event_player_id(
                    event
                )
            )

            if player_id not in player_lookup:
                continue

            player = player_lookup[
                player_id
            ]

            if is_own_goal(
                event
            ):
                title = "🔴 OWN GOAL"

            elif is_penalty_event(
                event
            ):
                title = "⚽ PENALTY GOAL"

            else:
                title = "⚽ GOAL"

            message = (
                f"{title}\n\n"
                f"⚽ {home_name} vs "
                f"{away_name}\n\n"
                f"👤 {player['name']}\n"
                f"⏱️ {minute}"
            )

            assist_name = (
                get_assist_name(
                    event
                )
            )

            if assist_name:
                message += (
                    f"\n🅰️ Assist: "
                    f"{assist_name}"
                )

            score_str = (
                status.get(
                    "scoreStr"
                )
                or ""
            )

            if score_str:
                message += (
                    f"\n📊 Score: "
                    f"{score_str}"
                )

            send_telegram(
                message
            )

            print(
                f"  📱 Goal notification sent: "
                f"{player['name']}"
            )

            reported.append(
                event_key
            )

        # ----------------------------------------------------
        # CARD
        # ----------------------------------------------------

        elif event_type == "card":

            player_id = (
                get_event_player_id(
                    event
                )
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
                f"⚽ {home_name} vs "
                f"{away_name}\n\n"
                f"👤 {player['name']}\n"
                f"⏱️ {minute}"
            )

            send_telegram(
                message
            )

            print(
                f"  📱 Card notification sent: "
                f"{player['name']} — "
                f"{card}"
            )

            reported.append(
                event_key
            )

        # ----------------------------------------------------
        # SUBSTITUTION
        # ----------------------------------------------------

        elif event_type == "substitution":

            player_id = (
                get_event_player_id(
                    event
                )
            )

            swap_players = (
                get_swap_players(
                    event
                )
            )

            involved_ids = set()

            if player_id is not None:
                involved_ids.add(
                    player_id
                )

            for swap_player in swap_players:

                if swap_player["id"] is not None:
                    involved_ids.add(
                        swap_player["id"]
                    )

            tracked_involved = [
                player_lookup[
                    player_id
                ]
                for player_id
                in involved_ids
                if player_id
                in player_lookup
            ]

            if not tracked_involved:
                continue

            player_in, player_out = (
                determine_substitution(
                    event,
                    substitution_info
                )
            )

            if (
                player_in
                and player_out
            ):

                message = (
                    "🔄 SUBSTITUTION\n\n"
                    f"⚽ {home_name} vs "
                    f"{away_name}\n\n"
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
                    for player
                    in tracked_involved
                ]

                message = (
                    "🔄 SUBSTITUTION\n\n"
                    f"⚽ {home_name} vs "
                    f"{away_name}\n\n"
                    f"👤 {' / '.join(names)}\n"
                    f"⏱️ {minute}"
                )

            send_telegram(
                message
            )

            print(
                "  📱 Substitution "
                "notification sent."
            )

            reported.append(
                event_key
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
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    return " ".join(
        text.split()
    )


def find_player_stat(
    player_data,
    wanted_keys
):

    wanted = {
        normalize_stat_key(key)
        for key in wanted_keys
    }

    groups = (
        player_data.get(
            "stats"
        )
        or []
    )

    for group in groups:

        group_stats = (
            group.get(
                "stats"
            )
            if isinstance(
                group,
                dict
            )
            else None
        )

        if not group_stats:
            continue

        if isinstance(
            group_stats,
            dict
        ):

            for label, stat_data in (
                group_stats.items()
            ):

                possible_keys = {
                    normalize_stat_key(
                        label
                    )
                }

                if isinstance(
                    stat_data,
                    dict
                ):

                    if stat_data.get(
                        "key"
                    ):
                        possible_keys.add(
                            normalize_stat_key(
                                stat_data.get(
                                    "key"
                                )
                            )
                        )

                    if stat_data.get(
                        "title"
                    ):
                        possible_keys.add(
                            normalize_stat_key(
                                stat_data.get(
                                    "title"
                                )
                            )
                        )

                if not (
                    possible_keys
                    & wanted
                ):
                    continue

                if isinstance(
                    stat_data,
                    dict
                ):

                    nested = stat_data.get(
                        "stat"
                    )

                    if isinstance(
                        nested,
                        dict
                    ):
                        return nested.get(
                            "value"
                        )

                    if "value" in stat_data:
                        return stat_data.get(
                            "value"
                        )

                return stat_data

    return None


def get_player_match_stats(
    details,
    player_lookup
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

        results[player_id] = {
            "name": data.get(
                "name"
            )
            or player_lookup[
                player_id
            ]["name"],

            "minutes": find_player_stat(
                data,
                [
                    "Minutes played",
                    "minutes_played",
                    "minutes",
                ],
            ),

            "rating": find_player_stat(
                data,
                [
                    "FotMob rating",
                    "rating",
                ],
            ),

            "goals": find_player_stat(
                data,
                [
                    "Goals",
                    "goals",
                ],
            ),

            "assists": find_player_stat(
                data,
                [
                    "Assists",
                    "goal_assist",
                    "assists",
                ],
            ),

            "yellow_cards": find_player_stat(
                data,
                [
                    "Yellow card",
                    "yellow_card",
                    "yellow cards",
                ],
            ),

            "red_cards": find_player_stat(
                data,
                [
                    "Red card",
                    "red_card",
                    "red cards",
                ],
            ),
        }

    return results


def process_final_report(
    match,
    details,
    state,
    player_lookup,
):

    match_id = str(
        match["id"]
    )

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

    if not status.get(
        "finished"
    ):
        return

    if status.get(
        "cancelled"
    ):
        print(
            "  ⚠️ Match was cancelled; "
            "no final report."
        )
        return

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
        or "Final"
    )

    player_stats = (
        get_player_match_stats(
            details,
            player_lookup
        )
    )

    if not player_stats:
        print(
            "  No tracked player stats "
            "available for final report."
        )
        return

    reported = (
        state[
            "final_posts"
        ].setdefault(
            match_id,
            []
        )
    )

    for player_id, stats in (
        player_stats.items()
    ):

        player = player_lookup[
            player_id
        ]

        report_key = str(
            player_id
        )

        if report_key in reported:

            print(
                f"  ↪ Final report already sent: "
                f"{player['name']}"
            )

            continue

        minutes = stats.get(
            "minutes"
        )

        rating = stats.get(
            "rating"
        )

        goals = stats.get(
            "goals"
        )

        assists = stats.get(
            "assists"
        )

        yellow_cards = stats.get(
            "yellow_cards"
        )

        red_cards = stats.get(
            "red_cards"
        )

        # Do not report players who were listed
        # but never actually played.
        try:
            if (
                minutes is not None
                and float(minutes) <= 0
                and rating is None
            ):
                continue

        except (
            TypeError,
            ValueError
        ):
            pass

        message = (
            "🏁 FULL TIME\n\n"
            f"⚽ {home_name} "
            f"{score_str} "
            f"{away_name}\n\n"
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

        if goals is not None:
            try:
                if float(goals) > 0:
                    message += (
                        f"⚽ Goals: "
                        f"{goals}\n"
                    )
            except (
                TypeError,
                ValueError
            ):
                pass

        if assists is not None:
            try:
                if float(assists) > 0:
                    message += (
                        f"🅰️ Assists: "
                        f"{assists}\n"
                    )
            except (
                TypeError,
                ValueError
            ):
                pass

        if yellow_cards is not None:
            try:
                if float(
                    yellow_cards
                ) > 0:
                    message += (
                        f"🟨 Yellow cards: "
                        f"{yellow_cards}\n"
                    )
            except (
                TypeError,
                ValueError
            ):
                pass

        if red_cards is not None:
            try:
                if float(
                    red_cards
                ) > 0:
                    message += (
                        f"🟥 Red cards: "
                        f"{red_cards}\n"
                    )
            except (
                TypeError,
                ValueError
            ):
                pass

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

    # ========================================================
    # LIVE / MATCH MONITORING
    # ========================================================

    today = get_local_today()

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
    # PROCESS TODAY'S MATCHES
    # ========================================================

    for match in relevant_matches:

        match_id = match.get(
            "id"
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

        print(
            f"Checking: "
            f"{home_name} vs "
            f"{away_name}"
        )

        try:

            details = (
                get_match_details(
                    match_id
                )
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

            process_final_report(
                match,
                details,
                state,
                player_lookup,
            )

        except Exception as e:

            print(
                f"  ❌ Error processing match "
                f"{match_id}: {e}"
            )

    save_json(
        STATE_FILE,
        state
    )

    print(
        "💾 Bot state updated."
    )

    print("=" * 70)

    print(
        "LINEUP + LIVE EVENT + "
        "DAILY MATCHES + "
        "FINAL REPORT MONITORING COMPLETE"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
