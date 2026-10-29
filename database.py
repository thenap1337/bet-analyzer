import os
import hashlib
import pymysql
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "bet_analyzer")
INITIAL_BANKROLL = float(os.getenv("BANKROLL", 1000.0))

REQUIRED_COLUMNS = {
    "event_id": "VARCHAR(100) DEFAULT NULL",
    "sport_key": "VARCHAR(100) DEFAULT NULL",
    "commence_time": "DATETIME DEFAULT NULL",
    "status": "VARCHAR(20) NOT NULL DEFAULT 'OPEN'",
    "profit_euro": "DECIMAL(10, 2) NOT NULL DEFAULT 0.00",
    "settled_at": "DATETIME DEFAULT NULL",
}


def get_connection():
    try:
        return pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=3
        )
    except Exception as e:
        # Fallback-Meldung, falls DB lokal nicht erreichbar ist
        print(f"[WARNUNG] DB-Verbindung fehlgeschlagen: {e}")
        return None


def init_db() -> bool:
    """Stellt sicher, dass die Tabelle sent_alerts und alle Statistik-Spalten existieren."""
    conn = get_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_alerts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    bet_hash VARCHAR(64) NOT NULL UNIQUE,
                    event_id VARCHAR(100) DEFAULT NULL,
                    sport_key VARCHAR(100) DEFAULT NULL,
                    commence_time DATETIME DEFAULT NULL,
                    match_name VARCHAR(255) NOT NULL,
                    bookmaker VARCHAR(100) NOT NULL,
                    tip VARCHAR(100) NOT NULL,
                    quote DECIMAL(8, 2) NOT NULL,
                    fair_quote DECIMAL(8, 2) NOT NULL,
                    edge DECIMAL(6, 2) NOT NULL,
                    stake_euro DECIMAL(10, 2) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
                    profit_euro DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
                    settled_at DATETIME DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("SHOW COLUMNS FROM sent_alerts")
            existing_cols = {row["Field"] for row in cursor.fetchall()}

            for col_name, col_def in REQUIRED_COLUMNS.items():
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE sent_alerts ADD COLUMN {col_name} {col_def}")
        conn.commit()
        return True
    except Exception as e:
        print(f"[WARNUNG] DB-Schema-Prüfung fehlgeschlagen: {e}")
        return False
    finally:
        conn.close()


def parse_iso_to_utc_naive(iso_str: str):
    """Konvertiert einen ISO-8601-String (z.B. '2026-10-30T14:30:00Z') in ein naives UTC-Datetime für MySQL."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return None


def generate_bet_hash(match: str, bookie: str, tip: str, quote: float) -> str:
    """Erzeugt einen eindeutigen Hash für diese spezifische Wettkonstellation."""
    raw = f"{match}_{bookie}_{tip}_{quote:.2f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_bet_already_sent(bet_hash: str) -> bool:
    """Prüft, ob der Alert für genau diese Quote bereits rausging."""
    conn = get_connection()
    if not conn:
        return False  # Falls keine DB da ist, Alert trotzdem erlauben

    try:
        with conn.cursor() as cursor:
            sql = "SELECT id FROM sent_alerts WHERE bet_hash = %s"
            cursor.execute(sql, (bet_hash,))
            result = cursor.fetchone()
            return result is not None
    finally:
        conn.close()


def is_tip_already_tracked(event_id: str, match: str, tip: str) -> bool:
    """
    Prüft, ob für dasselbe Spiel und denselben Tipp (Ausgang) bereits eine Wette
    in der Bankroll-Statistik platziert wurde (verhindert Doppel-Einsätze auf dasselbe Ergebnis).
    """
    conn = get_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            if event_id:
                sql = "SELECT id FROM sent_alerts WHERE event_id = %s AND tip = %s LIMIT 1"
                cursor.execute(sql, (event_id, tip))
            else:
                sql = "SELECT id FROM sent_alerts WHERE match_name = %s AND tip = %s LIMIT 1"
                cursor.execute(sql, (match, tip))
            return cursor.fetchone() is not None
    finally:
        conn.close()


def save_sent_bet(
    match: str,
    bookie: str,
    tip: str,
    quote: float,
    fair_quote: float,
    edge: float,
    stake: float,
    event_id: str = None,
    sport_key: str = None,
    commence_time: str = None,
) -> bool:
    """Speichert die gesendete Wette in MariaDB ab."""
    conn = get_connection()
    if not conn:
        return False

    bet_hash = generate_bet_hash(match, bookie, tip, quote)
    commence_dt = parse_iso_to_utc_naive(commence_time)

    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO sent_alerts 
                (bet_hash, event_id, sport_key, commence_time, match_name, bookmaker, tip, quote, fair_quote, edge, stake_euro, status, profit_euro)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'OPEN', 0.00)
            """
            cursor.execute(
                sql,
                (bet_hash, event_id, sport_key, commence_dt, match, bookie, tip, quote, fair_quote, edge, stake)
            )
        conn.commit()
        return True
    except pymysql.err.IntegrityError:
        return False  # Bereits vorhanden
    except Exception as e:
        print(f"Fehler beim Speichern in DB: {e}")
        return False
    finally:
        conn.close()


def get_open_bets() -> list:
    """Gibt alle noch nicht ausgewerteten Wetten (status = 'OPEN') zurück."""
    conn = get_connection()
    if not conn:
        return []

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM sent_alerts WHERE status = 'OPEN'")
            return cursor.fetchall()
    except Exception as e:
        print(f"Fehler beim Laden offener Wetten: {e}")
        return []
    finally:
        conn.close()


def update_bet_result(bet_id: int, status: str, profit_euro: float) -> bool:
    """Aktualisiert den Status ('WON', 'LOST', 'VOID') und den Netto-Gewinn/-Verlust einer Wette."""
    conn = get_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            sql = """
                UPDATE sent_alerts
                SET status = %s, profit_euro = %s, settled_at = UTC_TIMESTAMP()
                WHERE id = %s
            """
            cursor.execute(sql, (status, round(profit_euro, 2), bet_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Fehler beim Auswerten der Wette #{bet_id}: {e}")
        return False
    finally:
        conn.close()


def get_bankroll_stats(initial_bankroll: float = INITIAL_BANKROLL) -> dict:
    """
    Berechnet die aktuelle Bankroll-Entwicklung (Start: 1.000 €) und Statistik-Kennzahlen
    aus allen gespeicherten Wetten.
    """
    default_stats = {
        "initial_bankroll": round(initial_bankroll, 2),
        "current_bankroll": round(initial_bankroll, 2),
        "available_bankroll": round(initial_bankroll, 2),
        "net_profit": 0.0,
        "roi_percent": 0.0,
        "yield_percent": 0.0,
        "total_bets": 0,
        "settled_bets": 0,
        "open_bets": 0,
        "open_stake": 0.0,
        "won_bets": 0,
        "lost_bets": 0,
        "win_rate_percent": 0.0,
        "total_staked_settled": 0.0,
    }

    conn = get_connection()
    if not conn:
        return default_stats

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COUNT(*) AS total_bets,
                    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) AS open_bets,
                    COALESCE(SUM(CASE WHEN status = 'OPEN' THEN stake_euro ELSE 0 END), 0) AS open_stake,
                    SUM(CASE WHEN status = 'WON' THEN 1 ELSE 0 END) AS won_bets,
                    SUM(CASE WHEN status = 'LOST' THEN 1 ELSE 0 END) AS lost_bets,
                    COALESCE(SUM(CASE WHEN status IN ('WON', 'LOST') THEN stake_euro ELSE 0 END), 0) AS settled_stake,
                    COALESCE(SUM(CASE WHEN status IN ('WON', 'LOST') THEN profit_euro ELSE 0 END), 0) AS net_profit
                FROM sent_alerts
            """)
            row = cursor.fetchone()
            if not row or not row["total_bets"]:
                return default_stats

            total_bets = int(row["total_bets"] or 0)
            open_bets = int(row["open_bets"] or 0)
            open_stake = float(row["open_stake"] or 0.0)
            won_bets = int(row["won_bets"] or 0)
            lost_bets = int(row["lost_bets"] or 0)
            settled_bets = won_bets + lost_bets
            settled_stake = float(row["settled_stake"] or 0.0)
            net_profit = float(row["net_profit"] or 0.0)

            current_bankroll = round(initial_bankroll + net_profit, 2)
            available_bankroll = round(current_bankroll - open_stake, 2)
            roi_percent = round((net_profit / initial_bankroll) * 100, 2) if initial_bankroll > 0 else 0.0
            yield_percent = round((net_profit / settled_stake) * 100, 2) if settled_stake > 0 else 0.0
            win_rate = round((won_bets / settled_bets) * 100, 2) if settled_bets > 0 else 0.0

            return {
                "initial_bankroll": round(initial_bankroll, 2),
                "current_bankroll": current_bankroll,
                "available_bankroll": available_bankroll,
                "net_profit": round(net_profit, 2),
                "roi_percent": roi_percent,
                "yield_percent": yield_percent,
                "total_bets": total_bets,
                "settled_bets": settled_bets,
                "open_bets": open_bets,
                "open_stake": round(open_stake, 2),
                "won_bets": won_bets,
                "lost_bets": lost_bets,
                "win_rate_percent": win_rate,
                "total_staked_settled": round(settled_stake, 2),
            }
    except Exception as e:
        print(f"Fehler beim Berechnen der Bankroll-Statistik: {e}")
        return default_stats
    finally:
        conn.close()
