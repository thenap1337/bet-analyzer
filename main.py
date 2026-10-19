import os
import requests
from dotenv import load_dotenv
from bankroll import calculate_stake
from market_math import remove_margin
from notifier import send_discord_alert
from database import generate_bet_hash, is_bet_already_sent, save_sent_bet

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BANKROLL = float(os.getenv("BANKROLL", 1000))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", 0.25))

# Konfiguration
SPORT = "soccer_germany_bundesliga"
URL = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/"
MIN_EDGE_PERCENT = 2.0  # Mindest-Vorteil in Prozent
BENCHMARK_BOOKIE = "pinnacle"

# Erlaubte Buchmacher (leer lassen [], um alle zuzulassen)
ALLOWED_BOOKMAKERS = ["tipico_de"]

def fetch_market_odds():
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal"
    }
    response = requests.get(URL, params=params)
    if response.status_code != 200:
        print(f"Fehler beim Abruf: {response.status_code} - {response.text}")
        return []
        
    print(f"Verbleibende API-Requests: {response.headers.get('x-requests-remaining')}")
    return response.json()

def extract_h2h_quotes(bookmaker_data):
    """Extrahiert die 1X2 Quoten eines Buchmachers."""
    for market in bookmaker_data.get("markets", []):
        if market.get("key") == "h2h":
            quotes = {}
            for outcome in market.get("outcomes", []):
                quotes[outcome.get("name")] = outcome.get("price")
            return quotes
    return {}

def analyze_matches(matches):
    print(f"\n--- Starte Analyse für {len(matches)} Begegnungen ---")
    new_alerts_count = 0
    skipped_duplicates = 0

    for match in matches:
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
                fair_prob = fair_probs.get(outcome_name)
                if not fair_prob:
                    continue

                analysis = calculate_stake(BANKROLL, quote, fair_prob, KELLY_FRACTION)

                if analysis["is_value"] and analysis["edge_percent"] >= MIN_EDGE_PERCENT:
                    fair_quote = round(1.0 / fair_prob, 2)
                    bet_hash = generate_bet_hash(match_name, bookie_title, outcome_name, quote)

                    # Deduplizierung: Bereits in MariaDB vorhanden?
                    if is_bet_already_sent(bet_hash):
                        skipped_duplicates += 1
                        continue

                    new_alerts_count += 1
                    print(f"\n[NEUER VALUE BET]")
                    print(f"Spiel: {match_name}")
                    print(f"Buchmacher: {bookie_title} | Tipp: {outcome_name} @ {quote} (Fair: {fair_quote})")
                    print(f"Vorteil: +{analysis['edge_percent']}% | Einsatz: {analysis['stake_euro']} €")

                    alert_sent = send_discord_alert(
                        match=match_name,
                        bookie=bookie_title,
                        tip=outcome_name,
                        quote=quote,
                        fair_quote=fair_quote,
                        edge=analysis["edge_percent"],
                        stake=analysis["stake_euro"],
                        stake_pct=analysis["stake_percent"]
                    )

                    if alert_sent:
                        save_sent_bet(
                            match=match_name,
                            bookie=bookie_title,
                            tip=outcome_name,
                            quote=quote,
                            fair_quote=fair_quote,
                            edge=analysis["edge_percent"],
                            stake=analysis["stake_euro"]
                        )
                        print("-> Alert gesendet und in DB registriert.")

    print(f"\nDurchlauf abgeschlossen: {new_alerts_count} neue Alerts gesendet, {skipped_duplicates} bereits bekannte Wetten übersprungen.")

if __name__ == "__main__":
    odds_data = fetch_market_odds()
    if odds_data:
        analyze_matches(odds_data)