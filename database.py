import os
import hashlib
import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "bet_analyzer")

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

def save_sent_bet(match: str, bookie: str, tip: str, quote: float, fair_quote: float, edge: float, stake: float) -> bool:
    """Speichert die gesendete Wette in MariaDB ab."""
    conn = get_connection()
    if not conn:
        return False

    bet_hash = generate_bet_hash(match, bookie, tip, quote)

    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO sent_alerts 
                (bet_hash, match_name, bookmaker, tip, quote, fair_quote, edge, stake_euro)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (bet_hash, match, bookie, tip, quote, fair_quote, edge, stake))
        conn.commit()
        return True
    except pymysql.err.IntegrityError:
        return False  # Bereits vorhanden
    except Exception as e:
        print(f"Fehler beim Speichern in DB: {e}")
        return False
    finally:
        conn.close()