# 1. Wir nehmen ein fertiges, sauberes Mini-Linux mit Python 3.12
FROM python:3.12-slim

# 2. Wir erstellen einen Ordner "/app" in dieser Box
WORKDIR /app

# 3. Wir installieren kleine Werkzeuge, die für die Datenbank nötig sind
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 4. Wir kopieren deine "Goldene Liste" (requirements.txt) hinein
COPY requirements.txt .

# 5. Wir installieren genau diese Pakete IN die Box
RUN pip install --no-cache-dir -r requirements.txt

# 6. Wir kopieren deinen Code (runners und tests) hinein
COPY . .

# 7. Wir sagen der Box, wo sie deinen Code findet
ENV PYTHONPATH=/app/qa-runner/backend

# 8. Wenn die Box startet, soll sie sofort die 59 Tests machen
CMD ["pytest", "-v", "qa-runner/tests/"]
