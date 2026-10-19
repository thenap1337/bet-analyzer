import os
import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_alert(match: str, bookie: str, tip: str, quote: float, fair_quote: float, edge: float, stake: float, stake_pct: float) -> bool:
    """Sendet ein formatiertes Embed an einen Discord-Kanal via Webhook."""
    if not WEBHOOK_URL:
        print("Fehler: Keine DISCORD_WEBHOOK_URL in .env gefunden.")
        return False

    payload = {
        "username": "Value Bet Scanner",
        "embeds": [
            {
                "title": f"🎯 Value Bet: {match}",
                "color": 3066993,  # Grün (#2ecc71)
                "fields": [
                    {"name": "🏢 Buchmacher", "value": f"**{bookie}**", "inline": True},
                    {"name": "📌 Tipp", "value": f"**{tip}**", "inline": True},
                    {"name": "\u200b", "value": "\u200b", "inline": True},  # Leeres Feld für 2x2 Grid-Layout
                    {"name": "📈 Quote", "value": f"`{quote}` (Fair: `{fair_quote}`)", "inline": True},
                    {"name": "🚀 Edge", "value": f"`+{edge}%`", "inline": True},
                    {"name": "💰 Empf. Einsatz", "value": f"`{stake} €` ({stake_pct}%)", "inline": False}
                ],
                "footer": {
                    "text": "Bankroll-Management: Fractional Kelly"
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