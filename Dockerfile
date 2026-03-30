FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright/Firefox
RUN apt-get update && apt-get install -y \
    wget curl git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Firefox
RUN playwright install firefox --with-deps

# Copy app
COPY . .

EXPOSE 8080

CMD ["sh", "-c", "gunicorn main:app --timeout 120 --bind 0.0.0.0:${PORT:-8080}"]
