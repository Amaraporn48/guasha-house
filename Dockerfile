FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PORT=8000

# Set working directory
WORKDIR /app

# Install system dependencies needed for compiling certain python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    socat \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/

# Ensure uploads directory exists
RUN mkdir -p /app/static/uploads/slips /app/static/uploads/courses

# Expose application ports
EXPOSE 8000
EXPOSE 8080

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Start production server with dual port binding (both 8000 & 8080) so Railway routing never 502s
CMD ["sh", "-c", "APP_PORT=${PORT:-8000}; if [ \"$APP_PORT\" = \"8080\" ]; then (socat TCP-LISTEN:8000,fork,reuseaddr TCP:127.0.0.1:8080 &) 2>/dev/null; elif [ \"$APP_PORT\" = \"8000\" ]; then (socat TCP-LISTEN:8080,fork,reuseaddr TCP:127.0.0.1:8000 &) 2>/dev/null; fi; uvicorn main:app --host 0.0.0.0 --port ${APP_PORT} --workers 2 --proxy-headers --forwarded-allow-ips '*'"]
