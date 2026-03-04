FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PostGIS/geospatial libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libgeos-dev \
    libproj-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and migrations
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup appuser \
    && chown -R appuser:appgroup /app

# Set PYTHONPATH so uvicorn can find the app module
ENV PYTHONPATH=/app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8091

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]

