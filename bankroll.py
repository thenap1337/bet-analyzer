def round_to_half_euro(amount: float) -> float:
    """Rundet einen Euro-Betrag kaufmännisch auf die nächsten 0,50 € (Account-Schutz)."""
    return round(amount * 2.0) / 2.0


def calculate_stake(bankroll: float, quote: float, estimated_prob: float, fraction: float = 0.25) -> dict:
    """
    Berechnet den optimalen Einsatz nach dem Fractional-Kelly-Kriterium.
    - quote: Dezimalquote des Buchmachers (z.B. 2.10)
    - estimated_prob: Eigene Wahrscheinlichkeit als Dezimalwert (z.B. 0.52 für 52%)
    - fraction: Kelly-Dämpfungsfaktor (0.25 = Viertel-Kelly)
    Der empfohlene Einsatz in Euro wird auf 0,50 € gerundet, um Account-Limitierungen vorzubeugen.
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

    # Dämpfung anwenden und auf 0,50 € runden
    adjusted_fraction = kelly_f * fraction
    raw_stake_euro = bankroll * adjusted_fraction
    stake_euro = round(round_to_half_euro(raw_stake_euro), 2)

    return {
        "is_value": stake_euro > 0,
        "edge_percent": round((p * quote - 1.0) * 100, 2),
        "stake_euro": stake_euro,
        "stake_percent": round((stake_euro / bankroll) * 100, 2) if bankroll > 0 else 0.0
    }
