FROM python:3.10-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# System deps: Playwright needs some basics to run the install script
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install only Chromium and its dependencies (saves space/time)
RUN playwright install chromium --with-deps

# Copy code
COPY app.py .
COPY communicators ./communicators
COPY extractors ./extractors
COPY summarizers ./summarizers
COPY web_page_fetchers ./web_page_fetchers

EXPOSE 5001

CMD ["python", "app.py"]
