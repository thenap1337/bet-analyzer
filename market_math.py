def remove_margin(quotes: dict) -> dict:
    """
    Entfernt die Buchmachermarge (No-Vig) aus einem Markt (z. B. {'home': 2.10, 'draw': 3.40, 'away': 3.60}).
    Gibt die bereinigten, fairen Wahrscheinlichkeiten zurück.
    """
    implied_probs = {k: 1.0 / v for k, v in quotes.items() if v > 0}
    total_implied = sum(implied_probs.values())
    
    if total_implied == 0:
        return {}

    # Faire Wahrscheinlichkeit ohne Buchmacher-Aufschlag
    fair_probs = {k: p / total_implied for k, p in implied_probs.items()}
    return fair_probs