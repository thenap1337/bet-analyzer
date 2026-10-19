from database import get_connection, save_sent_bet, is_bet_already_sent, generate_bet_hash

def test():
    conn = get_connection()
    if not conn:
        print("❌ Verbindung zur Datenbank fehlgeschlagen!")
        return
    print("✅ Verbindung zur MariaDB erfolgreich!")
    conn.close()

    # Test-Eintrag schreiben
    test_match = "Test Team A vs Test Team B"
    test_bookie = "Tipico"
    test_tip = "Home"
    test_quote = 2.10
    
    test_hash = generate_bet_hash(test_match, test_bookie, test_tip, test_quote)
    print(f"Generierter Hash: {test_hash[:16]}...")

    if is_bet_already_sent(test_hash):
        print("ℹ️ Test-Wette existiert bereits in der Datenbank.")
    else:
        success = save_sent_bet(test_match, test_bookie, test_tip, test_quote, 2.00, 5.0, 10.0)
        if success:
            print("✅ Test-Wette erfolgreich in die Tabelle 'sent_alerts' geschrieben!")
        else:
            print("❌ Fehler beim Schreiben in die Datenbank.")

if __name__ == "__main__":
    test()