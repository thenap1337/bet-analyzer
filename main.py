import os
import requests
from dotenv import load_dotenv
from bankroll import calculate_stake

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")
BANKROLL = float(os.getenv("BANKROLL", 1000))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", 0.25))

# Beispiel: Deutsche Bundesliga (h2h = 1X2 Wetten)
SPORT = "soccer_germany_bundesliga"
URL = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds/"

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

def analyze_matches(matches):
    print(f"\n--- Analyse für {len(matches)} gefundene Spiele ---")
    
    for match in matches:
        home_team = match.get("home_team")
        away_team = match.get("away_team")
        
        # Buchmacher durchsuchen
        for bookmaker in match.get("bookmakers", []):
            title = bookmaker.get("title")
            
            # Wir suchen z. B. nach Tipico oder allgemeinen EU-Buchmachern
            for market in bookmaker.get("markets", []):
                if market.get("key") == "h2h":
                    for outcome in market.get("outcomes", []):
                        team = outcome.get("name")
                        quote = outcome.get("price")
                        
                        # --- PLATZHALTER FÜR DEIN STATISTIKMODELL ---
                        # Angenommen, dein Modell errechnet für den Heimsieg eine faire Quote von 1.85 (54% Chance)
                        # Hier setzen wir zum Testen eine statische Annahme:
                        assumed_prob = 0.50 
                        # ---------------------------------------------
                        
                        analysis = calculate_stake(BANKROLL, quote, assumed_prob, KELLY_FRACTION)
                        
                        if analysis["is_value"] and analysis["edge_percent"] > 3.0:  # Mind. 3% Vorteil
                            print(f"\n[VALUE BET GEFUNDEN bei {title}]")
                            print(f"Spiel: {home_team} vs {away_team}")
                            print(f"Tipp auf: {team} @ Quote {quote}")
                            print(f"Vorteil (Edge): +{analysis['edge_percent']}%")
                            print(f"Empfohlener Einsatz: {analysis['stake_euro']} € ({analysis['stake_percent']}% der Bankroll)")

if __name__ == "__main__":
    if not API_KEY or API_KEY == "dein_api_key_hier":
        print("Bitte trage zuerst deinen ODDS_API_KEY in die .env Datei ein!")
    else:
        odds_data = fetch_market_odds()
        if odds_data:
            analyze_matches(odds_data)