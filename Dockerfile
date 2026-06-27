FROM python:3.11-slim

# Instalar Chrome e dependências
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    gnupg \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Variáveis para o Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "algarve_monitor.py"]
