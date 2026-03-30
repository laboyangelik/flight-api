FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y wget curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright chromium (lightweight, for CDP connection to Steel)
RUN playwright install chromium --with-deps

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "gunicorn main:app --timeout 300 --bind 0.0.0.0:${PORT:-8080}"]
