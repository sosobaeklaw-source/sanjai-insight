# sanjai-insight Production Dockerfile
FROM python:3.12-slim

# Install dependencies
RUN apt-get update && apt-get install -y sqlite3 && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 appuser && mkdir -p /app/data && chown -R appuser:appuser /app

WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY --chown=appuser:appuser . .

USER appuser

# Run application (uvicorn FastAPI server)
CMD ["python", "-m", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
