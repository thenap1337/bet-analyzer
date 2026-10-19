FROM python:3.11-slim

WORKDIR /app

# Erst Abhängigkeiten kopieren und installieren (nutzt Docker-Layer-Caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den restlichen Code reinkopieren
COPY . .

# Befehl, der beim Start ausgeführt wird
CMD ["python", "main.py"]