import os
import time
import requests
from dotenv import load_dotenv
from bankroll import calculate_stake
from market_math import remove_margin
from notifier import send_discord_alert, send_bankroll_summary_discord
from database import (
    init_db,
    generate_bet_hash,
    is_bet_already_sent,
    is_tip_already_tracked,
    save_sent_bet,
    get_bankroll_stats,
)
from tracker import settle_open_bets, print_bankroll_report

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
INITIAL_BANKROLL = float(os.getenv("BANKROLL", 1000))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", 0.25))

# Liste der zu überwachenden Ligen
ACTIVE_SPORTS = [
    "soccer_germany_bundesliga",
    "soccer_germany_bundesliga2",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
]

MIN_EDGE_PERCENT = 2.0
BENCHMARK_BOOKIE = "pinnacle"
ALLOWED_BOOKMAKERS = ["tipico_de", "bet365", "bwin"]


def fetch_market_odds(sport_key):
    """Ruft Quoten für eine spezifische Liga ab."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"Fehler bei {sport_key}: {response.status_code} - {response.text}")
            return []

        remaining = response.headers.get("x-requests-remaining")
        print(f"[{sport_key}] Erfolgreich abgerufen. Verbleibende API-Requests: {remaining}")
        return response.json()
    except Exception as e:
        print(f"Netzwerkfehler bei {sport_key}: {e}")
        return []


def extract_h2h_quotes(bookmaker_data):
    for market in bookmaker_data.get("markets", []):
        if market.get("key") == "h2h":
            quotes = {}
            for outcome in market.get("outcomes", []):
                quotes[outcome.get("name")] = outcome.get("price")
            return quotes
    return {}


def analyze_matches(matches, league_name, current_bankroll: float):
    if not matches:
        return 0, 0

    print(f"Analysiere {len(matches)} Spiele in {league_name}...")
    new_alerts = 0
    duplicates = 0

    for match in matches:
        event_id = match.get("id")
        commence_time = match.get("commence_time")
        home_team = match.get("home_team")
        away_team = match.get("away_team")
        match_name = f"{home_team} vs. {away_team}"
        bookmakers = {b.get("key"): b for b in match.get("bookmakers", [])}

        if BENCHMARK_BOOKIE not in bookmakers:
            continue

        pinnacle_quotes = extract_h2h_quotes(bookmakers[BENCHMARK_BOOKIE])
        if len(pinnacle_quotes) < 3:
            continue

        fair_probs = remove_margin(pinnacle_quotes)

        # Sammle für dieses Spiel die jeweils höchste Quote pro Tipp unter den erlaubten Soft-Bookies
        best_offers_per_tip = {}

        for bookie_key, bookie_data in bookmakers.items():
            if bookie_key == BENCHMARK_BOOKIE:
                continue

            bookie_title = bookie_data.get("title", "")

            if ALLOWED_BOOKMAKERS:
                match_found = any(
                    target.lower() in bookie_key.lower() or target.lower() in bookie_title.lower()
                    for target in ALLOWED_BOOKMAKERS
                )
                if not match_found:
                    continue

            quotes = extract_h2h_quotes(bookie_data)

            for outcome_name, quote in quotes.items():
                if outcome_name not in best_offers_per_tip or quote > best_offers_per_tip[outcome_name]["quote"]:
                    best_offers_per_tip[outcome_name] = {
                        "bookie_title": bookie_title,
                        "quote": quote,
                    }

        # Prüfe nun pro Tipp das beste Angebot auf Value
        for outcome_name, offer in best_offers_per_tip.items():
            quote = offer["quote"]
            bookie_title = offer["bookie_title"]
            fair_prob = fair_probs.get(outcome_name)
            if not fair_prob:
                continue

            analysis = calculate_stake(current_bankroll, quote, fair_prob, KELLY_FRACTION)

            if analysis["is_value"] and analysis["edge_percent"] >= MIN_EDGE_PERCENT:
                fair_quote = round(1.0 / fair_prob, 2)
                bet_hash = generate_bet_hash(match_name, bookie_title, outcome_name, quote)

                # Prüfen, ob genau diese Wette oder bereits derselbe Tipp für dieses Spiel getrackt wurde
                if is_bet_already_sent(bet_hash) or is_tip_already_tracked(event_id, match_name, outcome_name):
                    duplicates += 1
                    continue

                new_alerts += 1
                print(
                    f"  -> VALUE GEFUNDEN: {match_name} ({commence_time}) | "
                    f"{outcome_name} @ {quote} bei {bookie_title} (+{analysis['edge_percent']}% | Einsatz: {analysis['stake_euro']:.2f} €)"
                )

                alert_sent = send_discord_alert(
                    match=f"[{league_name}] {match_name}",
                    bookie=bookie_title,
                    tip=outcome_name,
                    quote=quote,
                    fair_quote=fair_quote,
                    edge=analysis["edge_percent"],
                    stake=analysis["stake_euro"],
                    stake_pct=analysis["stake_percent"],
                    commence_time=commence_time,
                    current_bankroll=current_bankroll,
                )

                if alert_sent:
                    save_sent_bet(
                        match=match_name,
                        bookie=bookie_title,
                        tip=outcome_name,
                        quote=quote,
                        fair_quote=fair_quote,
                        edge=analysis["edge_percent"],
                        stake=analysis["stake_euro"],
                        event_id=event_id,
                        sport_key=league_name,
                        commence_time=commence_time,
                    )
    return new_alerts, duplicates


if __name__ == "__main__":
    print("=== INITIALISIERE DATENBANK & WERTUNG ===")
    init_db()

    # 1. Offene Wetten automatisch über The Odds API auswerten
    newly_settled = settle_open_bets(ACTIVE_SPORTS)

    # 2. Aktuellen Stand der 1.000-€-Bankroll abrufen
    stats_before = get_bankroll_stats(INITIAL_BANKROLL)
    current_bankroll = stats_before["current_bankroll"]
    print_bankroll_report(stats_before)

    # 3. Multi-Liga Value-Scan starten (mit dynamischer Bankroll)
    total_new = 0
    total_dupes = 0

    print("=== STARTE MULTI-LIGA ANALYSE ===")
    for sport in ACTIVE_SPORTS:
        data = fetch_market_odds(sport)
        new, dupes = analyze_matches(data, sport, current_bankroll)
        total_new += new
        total_dupes += dupes
        time.sleep(1)  # Kurze Pause zwischen den Liga-Requests

    print(f"\nDurchlauf beendet: {total_new} neue Alerts, {total_dupes} Duplikate übersprungen.")

    # 4. Falls Wetten ausgewertet oder neue Wetten platziert wurden, Statistik-Update an Discord senden
    stats_after = get_bankroll_stats(INITIAL_BANKROLL)
    if newly_settled or total_new > 0:
        send_bankroll_summary_discord(stats_after, newly_settled)
