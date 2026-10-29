import os
import requests
from dotenv import load_dotenv
from database import get_open_bets, update_bet_result, get_bankroll_stats, init_db
from notifier import send_bankroll_summary_discord

load_dotenv()

API_KEY = os.getenv("ODDS_API_KEY")


def fetch_league_scores(sport_key: str, days_from: int = 3) -> list:
    """Ruft die Ergebnisse der letzten `days_from` Tage für eine Liga über The Odds API ab."""
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/"
    params = {
        "apiKey": API_KEY,
        "daysFrom": days_from,
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            print(f"[Settlement] Fehler bei {sport_key} Scores: {response.status_code} - {response.text}")
            return []
        return response.json()
    except Exception as e:
        print(f"[Settlement] Netzwerkfehler bei {sport_key}: {e}")
        return []


def determine_h2h_winner(score_event: dict) -> str:
    """
    Ermittelt den Gewinner eines abgeschlossenen Spiels anhand der 'scores'-Liste von The Odds API.
    Gibt den Teamnamen des Siegers oder 'Draw' bei Unentschieden zurück (oder None, falls unvollständig).
    """
    if not score_event.get("completed"):
        return None

    scores = score_event.get("scores")
    if not scores or len(scores) < 2:
        return None

    home_team = score_event.get("home_team")
    away_team = score_event.get("away_team")

    score_map = {}
    for entry in scores:
        name = entry.get("name")
        try:
            score_map[name] = int(entry.get("score"))
        except (ValueError, TypeError):
            return None

    if home_team not in score_map or away_team not in score_map:
        return None

    home_goals = score_map[home_team]
    away_goals = score_map[away_team]

    if home_goals > away_goals:
        return home_team
    elif away_goals > home_goals:
        return away_team
    else:
        return "Draw"


def settle_open_bets(default_sports: list = None) -> list:
    """
    Prüft alle offenen Wetten in der Datenbank gegen die Ergebnisse von The Odds API
    und wertet beendete Spiele als WON oder LOST aus.
    Gibt eine Liste der neu ausgewerteten Wetten zurück.
    """
    open_bets = get_open_bets()
    if not open_bets:
        return []

    # Welche Ligen müssen abgefragt werden?
    sports_to_check = set()
    for bet in open_bets:
        if bet.get("sport_key"):
            sports_to_check.add(bet["sport_key"])
    if not sports_to_check and default_sports:
        sports_to_check.update(default_sports)

    if not sports_to_check:
        return []

    print(f"Prüfe Ergebnisse für {len(open_bets)} offene Wette(n) in {len(sports_to_check)} Liga/Ligen...")

    events_by_id = {}
    events_by_match_name = {}

    for sport_key in sports_to_check:
        score_events = fetch_league_scores(sport_key, days_from=3)
        for ev in score_events:
            if ev.get("id"):
                events_by_id[ev["id"]] = ev
            m_name = f"{ev.get('home_team')} vs. {ev.get('away_team')}"
            events_by_match_name[m_name] = ev

    newly_settled = []

    for bet in open_bets:
        event_id = bet.get("event_id")
        match_name = bet.get("match_name")

        score_ev = None
        if event_id and event_id in events_by_id:
            score_ev = events_by_id[event_id]
        elif match_name in events_by_match_name:
            score_ev = events_by_match_name[match_name]

        if not score_ev or not score_ev.get("completed"):
            continue

        winner = determine_h2h_winner(score_ev)
        if not winner:
            continue

        tip = bet.get("tip")
        stake = float(bet.get("stake_euro", 0.0))
        quote = float(bet.get("quote", 0.0))

        if tip == winner:
            status = "WON"
            profit = round(stake * (quote - 1.0), 2)
        else:
            status = "LOST"
            profit = round(-stake, 2)

        if update_bet_result(bet["id"], status, profit):
            sign = "+" if profit >= 0 else ""
            print(f"  [AUSGEWERTET] {match_name} | Tipp: {tip} -> {status} ({sign}{profit:.2f} €)")
            newly_settled.append({
                "id": bet["id"],
                "match": match_name,
                "tip": tip,
                "quote": quote,
                "stake": stake,
                "status": status,
                "profit": profit,
            })

    return newly_settled


def print_bankroll_report(stats: dict):
    """Gibt eine formatierte Übersicht der 1.000-€-Bankroll-Statistik in der Konsole aus."""
    profit = stats["net_profit"]
    sign = "+" if profit >= 0 else ""
    print("\n" + "=" * 55)
    print("💰 BANKROLL & PERFORMANCE TRACKER (Start: {:.2f} €)".format(stats["initial_bankroll"]))
    print("=" * 55)
    print(f"  Aktuelle Bankroll : {stats['current_bankroll']:.2f} € ({sign}{profit:.2f} € / {sign}{stats['roi_percent']:.2f}%)")
    print(f"  Verfügbar         : {stats['available_bankroll']:.2f} € (In offenen Wetten: {stats['open_stake']:.2f} €)")
    print(f"  Wetten gesamt     : {stats['total_bets']} ({stats['settled_bets']} ausgewertet, {stats['open_bets']} offen)")
    print(f"  Bilanz (S / N)    : {stats['won_bets']}W - {stats['lost_bets']}L (Trefferquote: {stats['win_rate_percent']:.1f}%)")
    print(f"  Yield (Umsatz)    : {sign}{stats['yield_percent']:.2f}% (bei {stats['total_staked_settled']:.2f} € Umsatz)")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    init_db()
    settled = settle_open_bets()
    current_stats = get_bankroll_stats()
    print_bankroll_report(current_stats)
    if settled:
        send_bankroll_summary_discord(current_stats, settled)

