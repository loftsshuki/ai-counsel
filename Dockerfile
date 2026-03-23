FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
# Use slim requirements for web deployment (no heavy ML packages)
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy application code
COPY . .

# Create directories
RUN mkdir -p /app/logs /app/transcripts /app/results

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

# Web UI (FastAPI + SSE streaming)
CMD ["python", "-m", "uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]
