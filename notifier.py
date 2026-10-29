import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def format_kickoff_discord(commence_time_iso: str) -> str:
    """
    Formatiert die ISO-Anstoßzeit (z.B. '2026-10-30T18:30:00Z') in eine lokale
    Zeitangabe inkl. dynamischem Discord-Zeitstempel (z.B. '30.10.2026, 19:30 Uhr (<t:1793385000:R>)').
    """
    if not commence_time_iso:
        return "Unbekannt"
    try:
        dt_utc = datetime.fromisoformat(commence_time_iso.replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone()
        unix_ts = int(dt_utc.timestamp())
        formatted_local = dt_local.strftime("%d.%m.%Y, %H:%M Uhr")
        return f"`{formatted_local}` (<t:{unix_ts}:R>)"
    except Exception:
        return commence_time_iso


def send_discord_alert(
    match: str,
    bookie: str,
    tip: str,
    quote: float,
    fair_quote: float,
    edge: float,
    stake: float,
    stake_pct: float,
    commence_time: str = None,
    current_bankroll: float = None,
) -> bool:
    """Sendet ein formatiertes Embed an einen Discord-Kanal via Webhook."""
    if not WEBHOOK_URL:
        print("Fehler: Keine DISCORD_WEBHOOK_URL in .env gefunden.")
        return False

    kickoff_str = format_kickoff_discord(commence_time)
    footer_text = "Bankroll-Management: Fractional Kelly (0,50 € Rundung)"
    if current_bankroll is not None:
        footer_text += f" | Aktuelle Bankroll: {current_bankroll:.2f} €"

    payload = {
        "username": "Value Bet Scanner",
        "embeds": [
            {
                "title": f"🎯 Value Bet: {match}",
                "color": 3066993,  # Grün (#2ecc71)
                "fields": [
                    {"name": "🕒 Anstoß", "value": kickoff_str, "inline": False},
                    {"name": "🏢 Buchmacher", "value": f"**{bookie}**", "inline": True},
                    {"name": "📌 Tipp", "value": f"**{tip}**", "inline": True},
                    {"name": "\u200b", "value": "\u200b", "inline": True},  # Leeres Feld für 2x2 Grid-Layout
                    {"name": "📈 Quote", "value": f"`{quote:.2f}` (Fair: `{fair_quote:.2f}`)", "inline": True},
                    {"name": "🚀 Edge", "value": f"`+{edge:.2f}%`", "inline": True},
                    {"name": "💰 Empf. Einsatz", "value": f"`{stake:.2f} €` ({stake_pct:.2f}%)", "inline": False}
                ],
                "footer": {
                    "text": footer_text
                }
            }
        ]
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        return response.status_code == 204
    except Exception as e:
        print(f"Fehler beim Senden an Discord: {e}")
        return False


def send_bankroll_summary_discord(stats: dict, newly_settled: list = None) -> bool:
    """Sendet eine Übersicht der aktuellen 1.000-€-Bankroll-Statistik an Discord."""
    if not WEBHOOK_URL:
        return False

    profit = stats.get("net_profit", 0.0)
    sign = "+" if profit >= 0 else ""
    color = 3066993 if profit >= 0 else 15158332  # Grün bei Plus, Rot bei Minus

    fields = [
        {
            "name": "💼 Aktuelle Bankroll",
            "value": f"**`{stats['current_bankroll']:.2f} €`** (Start: `{stats['initial_bankroll']:.2f} €`)",
            "inline": True
        },
        {
            "name": "📊 Gewinn / Verlust",
            "value": f"**`{sign}{profit:.2f} €`** (`{sign}{stats['roi_percent']:.2f}%` Bankroll)",
            "inline": True
        },
        {
            "name": "📈 Yield (Umsatzrendite)",
            "value": f"`{sign}{stats['yield_percent']:.2f}%`",
            "inline": True
        },
        {
            "name": "✅ Bilanz (S / N)",
            "value": f"`{stats['won_bets']}W` - `{stats['lost_bets']}L` (Trefferquote: `{stats['win_rate_percent']:.1f}%`)",
            "inline": True
        },
        {
            "name": "⏳ Offene Wetten",
            "value": f"`{stats['open_bets']}` (Gebunden: `{stats['open_stake']:.2f} €`)",
            "inline": True
        },
    ]

    if newly_settled:
        settled_lines = []
        for item in newly_settled[:5]:
            icon = "✅" if item["status"] == "WON" else "❌"
            p_sign = "+" if item["profit"] >= 0 else ""
            settled_lines.append(
                f"{icon} **{item['match']}** ({item['tip']} @ `{item['quote']:.2f}`) ➔ `{p_sign}{item['profit']:.2f} €`"
            )
        fields.append({
            "name": f"🏁 Neu ausgewertete Spiele ({len(newly_settled)})",
            "value": "\n".join(settled_lines),
            "inline": False
        })

    payload = {
        "username": "Value Bet Scanner",
        "embeds": [
            {
                "title": "📈 Bankroll & Performance-Statistik",
                "color": color,
                "fields": fields,
                "footer": {
                    "text": f"Ausgewertete Einsätze gesamt: {stats['total_staked_settled']:.2f} €"
                }
            }
        ]
    }

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=5)
        return response.status_code == 204
    except Exception as e:
        print(f"Fehler beim Senden des Statistik-Embeds: {e}")
        return False
