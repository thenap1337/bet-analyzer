def calculate_stake(bankroll: float, quote: float, estimated_prob: float, fraction: float = 0.25) -> dict:
    """
    Berechnet den optimalen Einsatz nach dem Fractional-Kelly-Kriterium.
    - quote: Dezimalquote des Buchmachers (z.B. 2.10)
    - estimated_prob: Eigene Wahrscheinlichkeit als Dezimalwert (z.B. 0.52 für 52%)
    - fraction: Kelly-Dämpfungsfaktor (0.25 = Viertel-Kelly)
    """
    b = quote - 1.0  # Netto-Quote
    p = estimated_prob
    q = 1.0 - p

    # Standard Kelly-Formel: f* = (b * p - q) / b
    kelly_f = (b * p - q) / b

    if kelly_f <= 0:
        return {
            "is_value": False,
            "edge_percent": round((p * quote - 1.0) * 100, 2),
            "stake_euro": 0.0,
            "stake_percent": 0.0
        }

    # Dämpfung anwenden
    adjusted_fraction = kelly_f * fraction
    stake_euro = round(bankroll * adjusted_fraction, 2)

    return {
        "is_value": True,
        "edge_percent": round((p * quote - 1.0) * 100, 2),
        "stake_euro": stake_euro,
        "stake_percent": round(adjusted_fraction * 100, 2)
    }