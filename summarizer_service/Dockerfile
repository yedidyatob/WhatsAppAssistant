FROM python:3.10-slim

WORKDIR /app

# System deps needed for Playwright
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps

# Copy code
COPY app.py .
COPY communicators ./communicators
COPY extractors ./extractors
COPY summarizers ./summarizers
COPY web_page_fetchers ./web_page_fetchers

EXPOSE 5001
ENV PYTHONPATH=/app

CMD ["python", "app.py"]
