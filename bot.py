import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests


# ============================================================
# CONFIG
# ============================================================

FOTMOB_BASE = "https://www.fotmob.com/api/data"
LOCAL_TIMEZONE = timezone(timedelta(hours=3, minutes=30))

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
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


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
# MATCH DISCOVERY
# ============================================================

def get_local_today():
    return datetime.now(timezone.utc).astimezone(LOCAL_TIMEZONE).date()


def get_today_matches():
    today = get_local_today()
    date_string = today.strftime("%Y%m%d")

    data = fotmob_get(
        "matches",
        {"date": date_string},
    )

    return data.get("leagues", [])


def collect_matches(leagues):
    matches = []

    for league in leagues:
        for match in league.get("matches", []):
            matches.append(match)

    return matches


# ============================================================
# TRACKED TEAMS
# ============================================================

def build_tracked_teams(players):
    tracked_teams = set()

    for player in players:
        club_id = player.get("team_id") or player.get("teamId")

        if club_id is not None:
            tracked_teams.add(int(club_id))

        if player.get("monitor_national_team"):
            national_team_id = (
                player.get("national_team_id")
                or player.get("nationalTeamId")
            )

            if national_team_id is not None:
                tracked_teams.add(int(national_team_id))

    return tracked_teams


def is_relevant_match(match, tracked_teams):
    home = match.get("home", {})
    away = match.get("away", {})

    home_id = home.get("id")
    away_id = away.get("id")

    if home_id is not None and int(home_id) in tracked_teams:
        return True

    if away_id is not None and int(away_id) in tracked_teams:
        return True

    return False


# ============================================================
# PLAYER LOOKUP
# ============================================================

def build_player_lookup(players):
    lookup = {}

    for player in players:
        player_id = player.get("fotmob_id")

        if player_id is not None:
            lookup[int(player_id)] = player

    return lookup


# ============================================================
# MATCH DETAILS
# ============================================================

def get_match_details(match_id):
    return fotmob_get(
        "matchDetails",
        {"matchId": match_id},
    )


# ============================================================
# LINEUP HELPERS
# ============================================================

def extract_lineup_players(lineup):
    players = {}

    if not lineup:
        return players

    for side_key in ["homeTeam", "awayTeam"]:
        side = lineup.get(side_key)

        if not side:
            continue

        for role, role_name in [
            ("starters", "STARTING XI"),
            ("subs", "BENCH"),
        ]:
            for player in side.get(role, []):
                player_id = player.get("id")

                if player_id is None:
                    continue

                players[int(player_id)] = {
                    "role": role_name,
                    "name": player.get("name", "Unknown"),
                    "team_id": side.get("id"),
                    "team_name": side.get("name"),
                    "timeSubbedOn": player.get("timeSubbedOn"),
                    "timeSubbedOff": player.get("timeSubbedOff"),
                    "events": player.get("events") or {},
                }

    return players


def process_confirmed_lineup(match, details, state, player_lookup):
    match_id = str(match["id"])

    content = details.get("content", {})
    lineup = content.get("lineup")

    if not lineup:
        print("  No lineup data available.")
        return

    lineup_type = lineup.get("lineupType")

    print(f"  Lineup type: {lineup_type}")

    if lineup_type != "standard":
        print("  ⏳ Lineup is not confirmed yet.")
        return

    lineup_players = extract_lineup_players(lineup)

    reported = state["lineup_notifications"].setdefault(
        match_id,
        []
    )

    for player_id, lineup_player in lineup_players.items():

        if player_id not in player_lookup:
            continue

        player = player_lookup[player_id]

        notification_key = (
            f"{player['name']}|{lineup_player['role']}"
        )

        if notification_key in reported:
            print(
                f"  ↪ Already reported: "
                f"{player['name']} ({lineup_player['role']})"
            )
            continue

        home_name = (
            match.get("home", {}).get("name", "Home")
        )
        away_name = (
            match.get("away", {}).get("name", "Away")
        )

        message = (
            "🔵 CONFIRMED LINEUP\n\n"
            f"⚽ {home_name} vs {away_name}\n\n"
            f"✅ {player['name']} — {lineup_player['role']}"
        )

        send_telegram(message)

        print(
            f"  📱 Telegram notification sent: "
            f"{player['name']} ({lineup_player['role']})"
        )

        reported.append(notification_key)


# ============================================================
# EVENT HELPERS
# ============================================================

def get_event_key(event):
    event_id = event.get("eventId")

    if event_id is not None:
        return f"id:{event_id}"

    event_type = str(event.get("type", "unknown"))
    minute = str(event.get("time", ""))
    player = event.get("player") or {}
    player_id = player.get("id", "")

    swaps = event.get("swap") or []
    swap_ids = ",".join(
        str(x.get("id", ""))
        for x in swaps
        if isinstance(x, dict)
    )

    card = str(event.get("card", ""))

    return (
        f"{event_type}|{minute}|"
        f"{player_id}|{swap_ids}|{card}"
    )


def get_event_player_id(event):
    player = event.get("player") or {}

    player_id = player.get("id")

    if player_id is None:
        return None

    try:
        return int(player_id)
    except (TypeError, ValueError):
        return None


def get_swap_players(event):
    swap_players = []

    for swap in event.get("swap") or []:
        if not isinstance(swap, dict):
            continue

        player_id = swap.get("id")
        name = swap.get("name")

        if player_id is not None:
            try:
                player_id = int(player_id)
            except (TypeError, ValueError):
                pass

        swap_players.append({
            "id": player_id,
            "name": name or "Unknown",
        })

    return swap_players


def get_minute(event):
    minute = event.get("time")

    if minute is None:
        minute = event.get("timeStr", "")

    overload = event.get("overloadTime")

    if overload:
        return f"{minute}+{overload}'"

    return f"{minute}'"


def normalize_card(card):
    if not card:
        return "CARD"

    card = str(card).strip().lower()

    if "second" in card and "yellow" in card:
        return "SECOND YELLOW"

    if "red" in card:
        return "RED CARD"

    if "yellow" in card:
        return "YELLOW CARD"

    return str(card).upper()


def is_penalty_event(event):
    text_parts = [
        str(event.get("goalDescription", "")),
        str(event.get("nameStr", "")),
        str(event.get("type", "")),
    ]

    combined = " ".join(text_parts).lower()

    return "penalty" in combined


def is_own_goal(event):
    own_goal = event.get("ownGoal")

    if own_goal is True:
        return True

    description = str(
        event.get("goalDescription", "")
    ).lower()

    return "own goal" in description


def get_assist_name(event):
    assist = event.get("assist")

    if isinstance(assist, dict):
        return (
            assist.get("name")
            or assist.get("playerName")
            or assist.get("fullName")
        )

    if isinstance(assist, str):
        return assist

    return (
        event.get("assistName")
        or event.get("assistPlayerName")
    )


# ============================================================
# SUBSTITUTION HELPERS
# ============================================================

def build_substitution_info(details):
    lineup = (
        details.get("content", {})
        .get("lineup")
        or {}
    )

    info = {}

    for side_key in ["homeTeam", "awayTeam"]:
        side = lineup.get(side_key)

        if not side:
            continue

        for role in ["starters", "subs"]:
            for player in side.get(role, []):
                player_id = player.get("id")

                if player_id is None:
                    continue

                try:
                    player_id = int(player_id)
                except (TypeError, ValueError):
                    continue

                events = player.get("events") or {}
                sub = events.get("sub") or {}

                info[player_id] = {
                    "name": player.get("name", "Unknown"),
                    "initial_role": role,
                    "timeSubbedOn": player.get("timeSubbedOn"),
                    "timeSubbedOff": player.get("timeSubbedOff"),
                    "subbedIn": sub.get("subbedIn"),
                    "subbedOut": sub.get("subbedOut"),
                }

    return info


def determine_substitution(event, substitution_info):
    swap_players = get_swap_players(event)

    if not swap_players:
        return None, None

    players_in = []
    players_out = []

    event_minute = event.get("time")

    for player in swap_players:
        player_id = player["id"]

        info = substitution_info.get(player_id)

        if not info:
            continue

        time_on = info.get("timeSubbedOn")
        time_off = info.get("timeSubbedOff")
        subbed_in = (
            (info.get("subbedIn") == event_minute)
            or (time_on == event_minute)
        )
        subbed_out = (
            (info.get("subbedOut") == event_minute)
            or (time_off == event_minute)
        )

        if subbed_in:
            players_in.append(player["name"])

        elif subbed_out:
            players_out.append(player["name"])

    if len(players_in) == 1 and len(players_out) == 1:
        return players_in[0], players_out[0]

    # Fallback based on initial lineup role.
    starters = []
    bench = []

    for player in swap_players:
        info = substitution_info.get(player["id"])

        if not info:
            continue

        if info.get("initial_role") == "subs":
            bench.append(player["name"])
        else:
            starters.append(player["name"])

    if len(bench) == 1 and len(starters) == 1:
        return bench[0], starters[0]

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
    match_id = str(match["id"])

    header = details.get("header", {})
    status = header.get("status") or {}

    started = bool(status.get("started"))
    finished = bool(status.get("finished"))

    if not started:
        return

    content = details.get("content", {})
    match_facts = content.get("matchFacts") or {}
    events_container = match_facts.get("events") or {}
    events = events_container.get("events") or []

    if not events:
        return

    reported = state["match_events"].setdefault(
        match_id,
        []
    )

    # Do not backfill a completed match on its first encounter.
    if finished and not reported:
        state["match_events"][match_id] = [
            get_event_key(event)
            for event in events
        ]

        print(
            "  ℹ️ Match already finished; "
            "existing events marked as seen."
        )
        return

    substitution_info = build_substitution_info(details)

    home_name = (
        match.get("home", {}).get("name", "Home")
    )
    away_name = (
        match.get("away", {}).get("name", "Away")
    )

    for event in events:

        event_key = get_event_key(event)

        if event_key in reported:
            continue

        event_type = str(
            event.get("type", "")
        ).strip().lower()

        minute = get_minute(event)

        # ----------------------------------------------------
        # GOAL
        # ----------------------------------------------------

        if event_type == "goal":

            player_id = get_event_player_id(event)

            if player_id not in player_lookup:
                continue

            player = player_lookup[player_id]

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

            assist_name = get_assist_name(event)

            if assist_name:
                message += f"\n🅰️ Assist: {assist_name}"

            score_str = (
                status.get("scoreStr")
                or ""
            )

            if score_str:
                message += f"\n📊 Score: {score_str}"

            send_telegram(message)

            print(
                f"  📱 Goal notification sent: "
                f"{player['name']}"
            )

            reported.append(event_key)

        # ----------------------------------------------------
        # CARD
        # ----------------------------------------------------

        elif event_type == "card":

            player_id = get_event_player_id(event)

            if player_id not in player_lookup:
                continue

            player = player_lookup[player_id]

            card = normalize_card(
                event.get("card")
            )

            # We monitor yellow/red cards.
            if card not in {
                "YELLOW CARD",
                "RED CARD",
                "SECOND YELLOW",
            }:
                continue

            emoji = "🟨"

            if card in {
                "RED CARD",
                "SECOND YELLOW",
            }:
                emoji = "🟥"

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

            reported.append(event_key)

        # ----------------------------------------------------
        # SUBSTITUTION
        # ----------------------------------------------------

        elif event_type == "substitution":

            player_id = get_event_player_id(event)

            swap_players = get_swap_players(event)

            involved_ids = set()

            if player_id is not None:
                involved_ids.add(player_id)

            for swap_player in swap_players:
                if swap_player["id"] is not None:
                    involved_ids.add(swap_player["id"])

            tracked_involved = [
                player_lookup[player_id]
                for player_id in involved_ids
                if player_id in player_lookup
            ]

            if not tracked_involved:
                continue

            player_in, player_out = determine_substitution(
                event,
                substitution_info,
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
                    player.get("name", "Unknown")
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

            reported.append(event_key)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("BARCELONA PLAYER BOT")
    print("=" * 70)

    players = load_json(
        PLAYERS_FILE,
        [],
    )

    state = load_json(
        STATE_FILE,
        {
            "daily_posts": [],
            "lineup_notifications": {},
            "match_events": {},
            "final_posts": {},
        },
    )

    # Make sure old state files get the required sections.
    state.setdefault("daily_posts", [])
    state.setdefault("lineup_notifications", {})
    state.setdefault("match_events", {})
    state.setdefault("final_posts", {})

    player_lookup = build_player_lookup(players)
    tracked_teams = build_tracked_teams(players)

    print(
        f"Tracking {len(players)} players"
    )

    print(
        f"Tracking {len(tracked_teams)} club/national teams"
    )

    today = get_local_today()

    print(
        f"Checking tracked matches for {today}..."
    )

    leagues = get_today_matches()
    matches = collect_matches(leagues)

    relevant_matches = [
        match
        for match in matches
        if is_relevant_match(
            match,
            tracked_teams,
        )
    ]

    print(
        f"Found {len(relevant_matches)} relevant matches."
    )

    print("=" * 70)

    for match in relevant_matches:

        match_id = match.get("id")

        home_name = (
            match.get("home", {}).get("name", "Home")
        )
        away_name = (
            match.get("away", {}).get("name", "Away")
        )

        print(
            f"Checking: {home_name} vs {away_name}"
        )

        try:
            details = get_match_details(match_id)

            # -----------------------------
            # CONFIRMED LINEUP
            # -----------------------------

            process_confirmed_lineup(
                match,
                details,
                state,
                player_lookup,
            )

            # -----------------------------
            # LIVE EVENTS
            # -----------------------------

            process_match_events(
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
        state,
    )

    print("💾 Bot state updated.")

    print("=" * 70)
    print("LINEUP + LIVE EVENT MONITORING COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
